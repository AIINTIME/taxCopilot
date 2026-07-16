"""The actual LangGraph implementation wiring the full query flow:

    intent classify -> temporal resolve
        -> (computation engine | hybrid retriever -> llm_client -> evidence gate)
        -> assemble_response -> audit_log_node

Node functions here are thin wrappers that call straight into services/* --
this file contains no business logic itself, only graph wiring and state
plumbing, per the orchestration-layer rule.
"""

import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.orchestration.nodes.assemble_response import assemble_response
from app.orchestration.nodes.audit_log_node import write_audit_log
from app.orchestration.state import QueryGraphState
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
from app.services.rag.llm_client import generate_narrative
from app.services.rag.prompts import CITATION_MANDATE, SYSTEM_PROMPT_TEMPLATE, build_context_block
from app.services.rag.retriever.hybrid_retriever import RetrievedChunk, hybrid_search
from app.shared.llm.base import LLMMessage


async def _classify_intent_node(state: QueryGraphState) -> dict:
    return {"intent": await classify_intent(state["query"])}


async def _resolve_temporal_node(state: QueryGraphState) -> dict:
    as_of = resolve_as_of(state["query"], state.get("explicit_as_of_date"))
    return {"as_of": as_of}


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


async def _computation_node(state: QueryGraphState) -> dict:
    rule_name = _infer_rule_name(state["query"])
    if rule_name is None:
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

    try:
        trace = compute(rule_name, inputs, state["as_of"])
    except MissingComputationInputError as exc:
        return {
            "computation_result": {
                "status": "missing_data",
                "rule_name": rule_name,
                "missing_fields": exc.missing_fields,
            }
        }

    return {"computation_result": {"status": "computed", "trace": trace.model_dump(mode="json")}}


async def _retrieval_node(state: QueryGraphState) -> dict:
    chunks = await hybrid_search(state["query"], state["as_of"])
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

    response = await generate_narrative(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=state["query"])],
    )
    return {"llm_response": response.model_dump()}


async def _evidence_gate_node(state: QueryGraphState) -> dict:
    llm_response = state.get("llm_response") or {}
    raw_text = llm_response.get("text", "")
    retrieved_chunks = [RetrievedChunk(**c) for c in state.get("retrieved_chunks", [])]

    if raw_text.strip() == INSUFFICIENT_SOURCES_MESSAGE:
        return {
            "gated_citations": [],
            "gate_status": "VERIFIED",
            "llm_response": {**llm_response, "text": raw_text},
        }

    extracted = extract_citations(raw_text, retrieved_chunks)
    gated_citations, gate_status = verify_citations(extracted, retrieved_chunks)
    gated_citations = await resolve_document_names(gated_citations)
    final_text = strip_unverified_claims(raw_text, gated_citations)

    return {
        "gated_citations": gated_citations,
        "gate_status": gate_status,
        "llm_response": {**llm_response, "text": final_text},
    }


def _route_after_temporal(state: QueryGraphState) -> str:
    # TODO: Intent.BOTH should traverse both branches; for now it is routed
    # through retrieval, same as Intent.RETRIEVAL, pending a fan-out design.
    if state["intent"] == Intent.COMPUTATION:
        return "computation"
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
    missing (MissingComputationInputError) is a genuinely different,
    actionable case -- the system knows exactly what's needed, it just needs
    numbers a human must supply -- so that one keeps going straight to
    assemble_response rather than being treated as a routing miss."""
    result = state.get("computation_result") or {}
    if result.get("status") == "missing_data" and "rule_name" not in result:
        return "computation_fallback"
    return "assemble_response"


def build_query_graph():
    graph = StateGraph(QueryGraphState)
    graph.add_node("classify_intent", _classify_intent_node)
    graph.add_node("resolve_temporal", _resolve_temporal_node)
    graph.add_node("computation", _computation_node)
    graph.add_node("computation_fallback", _clear_computation_fallback_node)
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
        {"computation": "computation", "retrieval": "retrieval"},
    )
    graph.add_conditional_edges(
        "computation",
        _route_after_computation,
        {"computation_fallback": "computation_fallback", "assemble_response": "assemble_response"},
    )
    graph.add_edge("computation_fallback", "retrieval")
    graph.add_edge("retrieval", "narrate")
    graph.add_edge("narrate", "evidence_gate")
    graph.add_edge("evidence_gate", "assemble_response")
    graph.add_edge("assemble_response", "audit_log")
    graph.add_edge("audit_log", END)

    return graph.compile()


# Built once at import time -- building/compiling the graph only wires node
# names and edges together, it does not invoke any node body, so the
# NotImplementedError stubs above do not fire until a query actually runs.
_compiled_graph = build_query_graph()


async def run_query_graph(domain: str, request: Any, user_id: str) -> dict:
    initial_state: QueryGraphState = {
        "query": request.query,
        "domain": domain,
        "user_id": user_id,
        "session_id": request.session_id,
        "explicit_as_of_date": request.as_of_date,
        "computation_inputs": getattr(request, "computation_inputs", None),
    }

    final_state = await _compiled_graph.ainvoke(initial_state)

    return {
        **final_state["final_response"],
        "audit_log_id": final_state["audit_entry"]["id"],
    }
