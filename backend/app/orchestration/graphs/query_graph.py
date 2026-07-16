"""The actual LangGraph implementation wiring the full query flow:

    intent classify -> temporal resolve
        -> [uploaded document?] -> document_extraction -> computation
        -> [computation_request given] -> computation
        -> [pure text query] -> retrieval -> narrate -> evidence_gate
    computation -> ground_truth_check -> assemble_response -> audit_log
    evidence_gate -> assemble_response -> audit_log

Node functions here are thin wrappers that call straight into services/* --
this file contains no business logic itself, only graph wiring and state
plumbing, per the orchestration-layer rule.
"""

import json
import logging
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.orchestration.nodes.assemble_response import assemble_response
from app.orchestration.nodes.audit_log_node import write_audit_log
from app.orchestration.state import QueryGraphState
from app.services.computation.computation_trace import ComputationTrace
from app.services.computation.engine import compute
from app.services.query.intent_classifier import Intent, classify_intent
from app.services.query.temporal_resolver import resolve_as_of
from app.services.rag.evidence_gate import verify_citations
from app.services.rag.extraction.document_extraction import (
    extract_capital_gains_inputs,
    verified_fields_to_computation_inputs,
)
from app.services.rag.ground_truth_gate import (
    derive_ground_truth_keywords,
    verify_computation_ground_truth,
)
from app.services.rag.llm_client import generate_narrative
from app.services.rag.prompts.narration_prompts import NARRATION_SYSTEM_PROMPT
from app.services.rag.retriever.graph_store import lookup_rate_rule
from app.services.rag.retriever.hybrid_retriever import RetrievedChunk, hybrid_search
from app.shared.llm.base import LLMMessage
from app.shared.schemas.citation import Citation

logger = logging.getLogger(__name__)

_DEFAULT_DOCUMENT_RULE_NAME = "capital_gains"


async def _classify_intent_node(state: QueryGraphState) -> dict:
    intent = classify_intent(state["query"])
    logger.info("[FLOW] classify_intent: query=%r -> intent=%s", state["query"], intent.value)
    return {"intent": intent}


async def _resolve_temporal_node(state: QueryGraphState) -> dict:
    as_of = resolve_as_of(state["query"], state.get("explicit_as_of_date"))
    logger.info(
        "[FLOW] resolve_temporal: as_of_date=%s regime=%s capital_gains_period=%s",
        as_of.as_of_date, as_of.regime.value, as_of.capital_gains_period.value,
    )
    return {"as_of": as_of}


async def _document_extraction_node(state: QueryGraphState) -> dict:
    logger.info("[FLOW] document_extraction: calling OpenAI LLM to extract fields from uploaded document")
    extracted = await extract_capital_gains_inputs(state["uploaded_document_text"])
    inputs, missing = verified_fields_to_computation_inputs(extracted)
    logger.info(
        "[FLOW] document_extraction: verified_fields=%s missing_fields=%s",
        list(inputs), missing,
    )

    result: dict[str, Any] = {
        "extracted_inputs": inputs,
        "extraction_missing_fields": missing,
    }
    # Only auto-build a computation_request when every required field was
    # verified, and only if the caller didn't already supply one explicitly.
    if not missing and state.get("computation_request") is None:
        result["computation_request"] = {
            "rule_name": _DEFAULT_DOCUMENT_RULE_NAME,
            "inputs": inputs,
        }
    return result


async def _computation_node(state: QueryGraphState) -> dict:
    computation_request = state.get("computation_request")
    if computation_request is None:
        missing = state.get("extraction_missing_fields") or []
        logger.warning("[FLOW] computation: BLOCKED, no computation_request (missing=%s)", missing)
        raise ValueError(
            "No computation_request is available and document extraction did "
            f"not verify every required field (missing: {missing}) -- the "
            "computation engine never runs on unverified or guessed figures; "
            "ask the user to confirm or supply these fields directly"
        )

    logger.info(
        "[FLOW] computation: hitting deterministic engine (no network) rule_name=%s inputs=%s",
        computation_request["rule_name"], computation_request["inputs"],
    )
    trace = compute(
        computation_request["rule_name"], computation_request["inputs"], state["as_of"]
    )
    logger.info("[FLOW] computation: result outputs=%s", trace.outputs)
    return {"computation_result": trace.model_dump()}


async def _ground_truth_check_node(state: QueryGraphState) -> dict:
    trace = ComputationTrace.model_validate(state["computation_result"])
    keywords = derive_ground_truth_keywords(trace.rule_name, trace.outputs)
    logger.info("[FLOW] ground_truth_check: derived keywords=%s", keywords)

    # The ground-truth check is a cross-check, not a dependency the response
    # can't exist without -- the computation result is already final and
    # correct on its own. A Neo4j/vector-store outage should degrade to "no
    # ground truth available" (same as an empty/unpopulated store), never
    # take down a response the engine already computed correctly.
    try:
        logger.info("[FLOW] ground_truth_check: hitting Neo4j (graph_store.lookup_rate_rule)")
        graph_rules = await lookup_rate_rule(keywords) if keywords else []
        logger.info("[FLOW] ground_truth_check: Neo4j returned %d matching rule(s)", len(graph_rules))
    except Exception:
        logger.exception("[FLOW] ground_truth_check: Neo4j lookup FAILED, degrading to no rules")
        graph_rules = []

    try:
        logger.info("[FLOW] ground_truth_check: hitting Pinecone (hybrid_search -> vector_store.similarity_search)")
        chunks = await hybrid_search(state["query"], state["as_of"])
        logger.info("[FLOW] ground_truth_check: Pinecone returned %d chunk(s)", len(chunks))
    except Exception:
        logger.exception("[FLOW] ground_truth_check: Pinecone lookup FAILED, degrading to no chunks")
        chunks = []

    check = verify_computation_ground_truth(trace, chunks, graph_rules)
    logger.info(
        "[FLOW] ground_truth_check: verified=%s mismatches=%d",
        check.verified, len(check.mismatches),
    )

    return {
        "graph_rules": graph_rules,
        "retrieved_chunks": [c.model_dump() for c in chunks],
        "ground_truth_check": check.model_dump(),
    }


async def _retrieval_node(state: QueryGraphState) -> dict:
    logger.info("[FLOW] retrieval: hitting Pinecone (hybrid_search -> vector_store.similarity_search)")
    chunks = await hybrid_search(state["query"], state["as_of"])
    logger.info("[FLOW] retrieval: Pinecone returned %d chunk(s)", len(chunks))
    return {"retrieved_chunks": [c.model_dump() for c in chunks]}


async def _narrate_node(state: QueryGraphState) -> dict:
    chunks = state.get("retrieved_chunks", [])
    context_text = "\n\n".join(f"[{c['chunk_id']}] {c['content']}" for c in chunks)
    user_message = f"Question: {state['query']}\n\nRetrieved statutory text:\n{context_text}"

    logger.info("[FLOW] narrate: hitting OpenAI LLM (services.rag.llm_client.generate_narrative) with %d chunk(s) of context", len(chunks))
    response = await generate_narrative(
        system_prompt=NARRATION_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=user_message)],
    )
    logger.info("[FLOW] narrate: LLM response received, provider=%s model=%s", response.provider_name, response.model_version)
    return {"llm_response": response.model_dump()}


_CITATIONS_BLOCK_PATTERN = re.compile(r"CITATIONS:\s*(\[.*\])", re.DOTALL)


def _parse_citations(narration_text: str, retrieved_chunks: list[dict]) -> list[Citation]:
    match = _CITATIONS_BLOCK_PATTERN.search(narration_text)
    if not match:
        return []
    try:
        raw_citations = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    if not isinstance(raw_citations, list):
        return []

    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in retrieved_chunks}
    citations: list[Citation] = []
    for item in raw_citations:
        if not isinstance(item, dict):
            continue
        chunk_id, excerpt = item.get("chunk_id"), item.get("excerpt")
        chunk = chunks_by_id.get(chunk_id)
        if not chunk_id or not excerpt or chunk is None:
            continue
        citations.append(
            Citation(
                chunk_id=chunk_id,
                source_id=chunk.get("source_id", ""),
                section_reference=chunk.get("section_reference"),
                excerpt=excerpt,
                confidence=0.5,
                verified=False,
            )
        )
    return citations


async def _evidence_gate_node(state: QueryGraphState) -> dict:
    llm_response = state.get("llm_response") or {}
    narration_text = llm_response.get("text", "")
    citations = _parse_citations(narration_text, state.get("retrieved_chunks", []))
    retrieved_chunks = [RetrievedChunk(**c) for c in state.get("retrieved_chunks", [])]

    verified_citations, gate_status = verify_citations(citations, retrieved_chunks)
    logger.info(
        "[FLOW] evidence_gate: %d citation(s) proposed, %d verified, gate_status=%s",
        len(citations), len(verified_citations), gate_status,
    )
    return {
        "gated_citations": [c.model_dump() for c in verified_citations],
        "gate_status": gate_status,
    }


def _route_after_temporal(state: QueryGraphState) -> str:
    if state.get("uploaded_document_text"):
        logger.info("[FLOW] route_after_temporal: document attached -> document_extraction -> computation")
        return "document_extraction"
    if state.get("computation_request") is not None:
        logger.info("[FLOW] route_after_temporal: computation_request given -> computation (+ ground_truth_check)")
        return "computation"
    if state["intent"] == Intent.COMPUTATION:
        logger.info(
            "[FLOW] route_after_temporal: intent=COMPUTATION but no computation_request/document -- "
            "will raise in computation node (no free-text-to-numbers parser exists)"
        )
        return "computation"
    # TODO: Intent.BOTH should traverse both branches; for now it is routed
    # through retrieval, same as Intent.RETRIEVAL, pending a fan-out design.
    logger.info("[FLOW] route_after_temporal: -> retrieval -> narrate -> evidence_gate")
    return "retrieval"


def build_query_graph():
    graph = StateGraph(QueryGraphState)
    graph.add_node("classify_intent", _classify_intent_node)
    graph.add_node("resolve_temporal", _resolve_temporal_node)
    graph.add_node("document_extraction", _document_extraction_node)
    graph.add_node("computation", _computation_node)
    graph.add_node("ground_truth_check", _ground_truth_check_node)
    graph.add_node("retrieval", _retrieval_node)
    graph.add_node("narrate", _narrate_node)
    graph.add_node("evidence_gate", _evidence_gate_node)
    graph.add_node("assemble_response", assemble_response)
    graph.add_node("audit_log", write_audit_log)

    graph.add_edge(START, "classify_intent")
    graph.add_edge("classify_intent", "resolve_temporal")
    graph.add_conditional_edges(
        "resolve_temporal",
        _route_after_temporal,
        {
            "document_extraction": "document_extraction",
            "computation": "computation",
            "retrieval": "retrieval",
        },
    )
    graph.add_edge("document_extraction", "computation")
    graph.add_edge("computation", "ground_truth_check")
    graph.add_edge("ground_truth_check", "assemble_response")
    graph.add_edge("retrieval", "narrate")
    graph.add_edge("narrate", "evidence_gate")
    graph.add_edge("evidence_gate", "assemble_response")
    graph.add_edge("assemble_response", "audit_log")
    graph.add_edge("audit_log", END)

    return graph.compile()


# Built once at import time -- building/compiling the graph only wires node
# names and edges together, it does not invoke any node body, so a bad
# runtime path only ever surfaces when a query actually runs.
_compiled_graph = build_query_graph()


async def run_query_graph(domain: str, request: Any, user_id: str) -> dict:
    computation_request = getattr(request, "computation_request", None)
    if computation_request is not None and hasattr(computation_request, "model_dump"):
        computation_request = computation_request.model_dump()

    logger.info(
        "[FLOW] run_query_graph: ENTRY domain=%s query=%r has_computation_request=%s has_uploaded_document=%s",
        domain, request.query, computation_request is not None,
        bool(getattr(request, "uploaded_document_text", None)),
    )

    initial_state: QueryGraphState = {
        "query": request.query,
        "domain": domain,
        "user_id": user_id,
        "session_id": getattr(request, "session_id", None),
        "explicit_as_of_date": getattr(request, "as_of_date", None),
        "computation_request": computation_request,
        "uploaded_document_text": getattr(request, "uploaded_document_text", None),
    }
    final_state = await _compiled_graph.ainvoke(initial_state)
    logger.info(
        "[FLOW] run_query_graph: EXIT gate_status=%s audit_log_id=%s",
        final_state["final_response"].get("gate_status"),
        final_state["final_response"].get("audit_log_id"),
    )
    return final_state["final_response"]
