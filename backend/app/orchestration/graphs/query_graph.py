"""The actual LangGraph implementation wiring the full query flow:

    intent classify -> temporal resolve
        -> [uploaded document?] -> document_extraction -> computation
        -> [computation_request given] -> computation
        -> [free-text query, rule inferred] -> computation
        -> [pure text query / rule not inferred] -> retrieval -> narrate -> evidence_gate
    computation -> [computed] -> ground_truth_check -> assemble_response -> audit_log
    computation -> [rule not inferred at all] -> computation_fallback -> retrieval
    computation -> [rule known but fields missing] -> assemble_response -> audit_log
    evidence_gate -> assemble_response -> audit_log

Node functions here are thin wrappers that call straight into services/* --
this file contains no business logic itself, only graph wiring and state
plumbing, per the orchestration-layer rule.
"""

import logging
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.orchestration.nodes.assemble_response import assemble_response
from app.orchestration.nodes.audit_log_node import write_audit_log
from app.orchestration.state import QueryGraphState
from app.services.computation.computation_trace import ComputationTrace
from app.services.computation.engine import MissingComputationInputError, compute
from app.services.query.intent_classifier import Intent, classify_intent
from app.services.query.temporal_resolver import resolve_as_of
from app.services.rag.document_lookup import resolve_document_names
from app.services.rag.evidence_gate import (
    INSUFFICIENT_SOURCES_MESSAGE,
    extract_citations,
    strip_unverified_claims,
    verify_citations,
)
from app.services.rag.extraction.document_extraction import (
    extract_capital_gains_inputs,
    verified_fields_to_computation_inputs,
)
from app.services.rag.ground_truth_gate import (
    derive_ground_truth_keywords,
    verify_computation_ground_truth,
)
from app.services.rag.llm_client import generate_narrative
from app.services.rag.prompts import CITATION_MANDATE, SYSTEM_PROMPT_TEMPLATE, build_context_block
from app.services.rag.retriever.graph_store import lookup_rate_rule
from app.services.rag.retriever.hybrid_retriever import RetrievedChunk, hybrid_search
from app.shared.llm.base import LLMMessage

logger = logging.getLogger(__name__)

_DEFAULT_DOCUMENT_RULE_NAME = "capital_gains"

_RULE_NAME_PATTERNS: dict[str, re.Pattern[str]] = {
    "mat": re.compile(r"\b(mat\b|minimum alternate tax|115jb)\b", re.IGNORECASE),
    "amt": re.compile(r"\b(amt\b|alternate minimum tax|115jc)\b", re.IGNORECASE),
    "regime_comparison": re.compile(r"\b(regime|115baa|115bab)\b", re.IGNORECASE),
    "depreciation": re.compile(r"\b(depreciation|wdv|written down value)\b", re.IGNORECASE),
    "capital_gains": re.compile(r"\b(capital gains?|ltcg|stcg|indexation)\b", re.IGNORECASE),
}


def _infer_rule_name(query: str) -> str | None:
    for rule_name, pattern in _RULE_NAME_PATTERNS.items():
        if pattern.search(query):
            return rule_name
    return None


async def _classify_intent_node(state: QueryGraphState) -> dict:
    intent = await classify_intent(state["query"])
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
    if computation_request is not None:
        rule_name = computation_request["rule_name"]
        inputs = computation_request["inputs"]
        logger.info(
            "[FLOW] computation: explicit computation_request rule_name=%s inputs=%s",
            rule_name, inputs,
        )
    else:
        rule_name = _infer_rule_name(state["query"])
        if rule_name is None:
            logger.info(
                "[FLOW] computation: no rule_name inferred from query -- falling back to retrieval"
            )
            return {
                "computation_result": {
                    "status": "missing_data",
                    "missing_fields": [
                        "which computation you want -- mention MAT, AMT, regime "
                        "comparison, depreciation, or capital gains explicitly"
                    ],
                }
            }
        inputs = state.get("computation_inputs") or {}
        logger.info(
            "[FLOW] computation: rule_name=%s inferred from query text, inputs=%s",
            rule_name, inputs,
        )

    try:
        trace = compute(rule_name, inputs, state["as_of"])
    except MissingComputationInputError as exc:
        logger.warning(
            "[FLOW] computation: missing required fields for rule_name=%s missing=%s",
            rule_name, exc.missing_fields,
        )
        return {
            "computation_result": {
                "status": "missing_data",
                "rule_name": rule_name,
                "missing_fields": exc.missing_fields,
            }
        }

    logger.info("[FLOW] computation: result outputs=%s", trace.outputs)
    return {"computation_result": {"status": "computed", "trace": trace.model_dump(mode="json")}}


async def _ground_truth_check_node(state: QueryGraphState) -> dict:
    trace = ComputationTrace.model_validate(state["computation_result"]["trace"])
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
        logger.info("[FLOW] ground_truth_check: hitting Pinecone/Neo4j (hybrid_search)")
        chunks = await hybrid_search(state["query"], state["as_of"])
        logger.info("[FLOW] ground_truth_check: hybrid_search returned %d chunk(s)", len(chunks))
    except Exception:
        logger.exception("[FLOW] ground_truth_check: hybrid_search FAILED, degrading to no chunks")
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
    logger.info("[FLOW] retrieval: hitting Pinecone/Neo4j (hybrid_search)")
    chunks = await hybrid_search(state["query"], state["as_of"])
    logger.info("[FLOW] retrieval: hybrid_search returned %d chunk(s)", len(chunks))
    return {"retrieved_chunks": [c.model_dump() for c in chunks]}


async def _clear_computation_fallback_node(state: QueryGraphState) -> dict:
    # Graph state is cumulative -- without this, a query that fell through
    # from computation to retrieval would still carry the earlier
    # "missing_data" computation_result, and assemble_response (which checks
    # computation_result first, unconditionally) would return the static
    # dead-end message instead of the real RAG answer this fallback exists
    # to produce.
    return {"computation_result": None}


async def _narrate_node(state: QueryGraphState) -> dict:
    context = build_context_block(state["retrieved_chunks"])
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context) + "\n\n" + CITATION_MANDATE

    logger.info(
        "[FLOW] narrate: hitting OpenAI LLM (services.rag.llm_client.generate_narrative) "
        "with %d chunk(s) of context", len(state["retrieved_chunks"]),
    )
    response = await generate_narrative(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=state["query"])],
    )
    logger.info(
        "[FLOW] narrate: LLM response received, provider=%s model=%s",
        response.provider_name, response.model_version,
    )
    return {"llm_response": response.model_dump()}


async def _evidence_gate_node(state: QueryGraphState) -> dict:
    llm_response = state.get("llm_response") or {}
    raw_text = llm_response.get("text", "")
    retrieved_chunks = [RetrievedChunk(**c) for c in state.get("retrieved_chunks", [])]

    if raw_text.strip() == INSUFFICIENT_SOURCES_MESSAGE:
        logger.info("[FLOW] evidence_gate: LLM reported insufficient sources")
        return {
            "gated_citations": [],
            "gate_status": "VERIFIED",
            "llm_response": {**llm_response, "text": raw_text},
        }

    extracted = extract_citations(raw_text, retrieved_chunks)
    gated_citations, gate_status = verify_citations(extracted, retrieved_chunks)
    gated_citations = await resolve_document_names(gated_citations)
    final_text = strip_unverified_claims(raw_text, gated_citations)
    logger.info(
        "[FLOW] evidence_gate: %d citation(s) proposed, gate_status=%s",
        len(extracted), gate_status,
    )

    return {
        "gated_citations": gated_citations,
        "gate_status": gate_status,
        "llm_response": {**llm_response, "text": final_text},
    }


def _route_after_temporal(state: QueryGraphState) -> str:
    if state.get("uploaded_document_text"):
        logger.info("[FLOW] route_after_temporal: document attached -> document_extraction -> computation")
        return "document_extraction"
    if state.get("computation_request") is not None:
        logger.info("[FLOW] route_after_temporal: computation_request given -> computation")
        return "computation"
    if state["intent"] == Intent.COMPUTATION:
        logger.info(
            "[FLOW] route_after_temporal: intent=COMPUTATION -> computation "
            "(rule_name will be inferred from the query text)"
        )
        return "computation"
    # TODO: Intent.BOTH should traverse both branches; for now it is routed
    # through retrieval, same as Intent.RETRIEVAL, pending a fan-out design.
    logger.info("[FLOW] route_after_temporal: -> retrieval -> narrate -> evidence_gate")
    return "retrieval"


def _route_after_computation(state: QueryGraphState) -> str:
    """A query that reaches the computation node but doesn't match one of the
    known rule names (_infer_rule_name returned None) isn't actually a
    dead end -- it just means routing guessed COMPUTATION for a query the
    deterministic engine has no rule for. Fall through to a real RAG search
    instead of stranding the user with a static "mention MAT/AMT/..."
    message; that message is only appropriate once we've also failed to find
    anything relevant in the vector DB.

    A query where the rule WAS identified but specific numeric inputs are
    missing (MissingComputationInputError, or an explicit computation_request
    that's simply incomplete) is a genuinely different, actionable case --
    the system knows exactly what's needed, it just needs numbers a human
    must supply -- so that one goes straight to assemble_response rather than
    being treated as a routing miss.

    A rule that DID compute successfully still needs the ground-truth
    cross-check against the statutory graph before the response is final."""
    result = state.get("computation_result") or {}
    if result.get("status") == "missing_data" and "rule_name" not in result:
        return "computation_fallback"
    if result.get("status") == "computed":
        return "ground_truth_check"
    return "assemble_response"


def build_query_graph():
    graph = StateGraph(QueryGraphState)
    graph.add_node("classify_intent", _classify_intent_node)
    graph.add_node("resolve_temporal", _resolve_temporal_node)
    graph.add_node("document_extraction", _document_extraction_node)
    graph.add_node("computation", _computation_node)
    graph.add_node("computation_fallback", _clear_computation_fallback_node)
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
    graph.add_conditional_edges(
        "computation",
        _route_after_computation,
        {
            "computation_fallback": "computation_fallback",
            "ground_truth_check": "ground_truth_check",
            "assemble_response": "assemble_response",
        },
    )
    graph.add_edge("computation_fallback", "retrieval")
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
        "computation_inputs": getattr(request, "computation_inputs", None),
    }
    final_state = await _compiled_graph.ainvoke(initial_state)
    logger.info(
        "[FLOW] run_query_graph: EXIT gate_status=%s audit_log_id=%s",
        final_state["final_response"].get("gate_status"),
        final_state["final_response"].get("audit_log_id"),
    )
    return final_state["final_response"]
