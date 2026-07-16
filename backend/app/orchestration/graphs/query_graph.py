"""The actual LangGraph implementation wiring the full query flow:

    classify intent -> extract inputs -> temporal resolve
        -> (clarify | computation [-> citations] | retrieval -> narrate -> gate)
        -> assemble_response -> audit_log

Node functions here are thin wrappers that call straight into services/* --
this file contains no business logic itself, only graph wiring and state
plumbing, per the orchestration-layer rule.

WHY Intent.BOTH IS A LINEAR CHAIN, NOT A FAN-OUT. The original TODO deferred
BOTH pending "a fan-out design", framing it as a parallelism problem. It isn't
one: computation is pure Python over in-memory rate tables and returns in
microseconds, while retrieval takes seconds (embedding call + Pinecone round
trip). Running them concurrently would save nothing measurable while buying
LangGraph reducer semantics and concurrent-write errors. Sequencing computation
FIRST also produces better narration -- the model receives the computed figures
alongside the retrieved text, which is exactly the shape rag/prompts expects.
"""

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.orchestration.nodes.assemble_response import assemble_response
from app.orchestration.nodes.audit_log_node import write_audit_log
from app.orchestration.nodes.computation_citations import resolve_computation_citations
from app.orchestration.state import QueryGraphState
from app.services.computation.engine import compute
from app.services.computation.rules.personal.slab_tables import PersonalRegime
from app.services.query.input_extractor import clarification_questions, extract_inputs
from app.services.query.intent_classifier import Intent, classify_intent
from app.services.query.rate_lookup import build_deduction_card, build_rate_card
from app.services.query.temporal_resolver import resolve_as_of
from app.services.rag.evidence_gate import verify_citations
from app.services.rag.llm_client import generate_narrative
from app.services.rag.prompts import build_narration_messages, parse_narration
from app.services.rag.retriever.hybrid_retriever import RetrievedChunk, hybrid_search

logger = logging.getLogger(__name__)

# The only rule the personal-tax domain computes today. Deliberately not
# inferred from the query text: engine.compute already rejects unknown rule
# names, and guessing a rule would be the same class of mistake as guessing an
# input.
_PERSONAL_RULE = "personal_regime_comparison"


async def _classify_intent_node(state: QueryGraphState) -> dict:
    return {"intent": classify_intent(state["query"])}


async def _extract_inputs_node(state: QueryGraphState) -> dict:
    extracted = extract_inputs(state["query"])

    # Missing inputs only block a computation. A retrieval question ("what is
    # HRA?") legitimately has no income figure and must not be interrogated
    # for one.
    blocking = (
        list(extracted.missing)
        if state["intent"] in (Intent.COMPUTATION, Intent.BOTH)
        else []
    )

    clarification = None
    if blocking:
        questions = clarification_questions(extracted)
        clarification = "\n".join(
            ["I need one more detail before I can compute this:", *questions]
        )

    return {
        "extracted_inputs": extracted.to_rule_inputs(),
        "assumptions": list(extracted.assumptions),
        "missing": blocking,
        "clarification": clarification,
    }


async def _resolve_temporal_node(state: QueryGraphState) -> dict:
    return {"as_of": resolve_as_of(state["query"], state.get("explicit_as_of_date"))}


async def _clarify_node(state: QueryGraphState) -> dict:
    # Nothing is asserted, so there is nothing to verify or cite.
    return {"gate_status": "VERIFIED", "gated_citations": []}


def _regime_in_query(query: str) -> PersonalRegime | None:
    lowered = query.lower()
    new_hit = "new regime" in lowered or "new tax regime" in lowered or "115bac" in lowered
    old_hit = "old regime" in lowered or "old tax regime" in lowered
    if new_hit and not old_hit:
        return PersonalRegime.NEW
    if old_hit and not new_hit:
        return PersonalRegime.OLD
    return None


async def _rate_lookup_node(state: QueryGraphState) -> dict:
    # Figures read straight from slab_tables -- no LLM, so the figure ban does
    # not apply and cannot block the answer. VERIFIED because the rate table is
    # authoritative and source-referenced, the same basis as computation.
    card = build_rate_card(state["as_of"], _regime_in_query(state["query"]))
    return {"rate_card": card, "gate_status": "VERIFIED", "gated_citations": []}


async def _deduction_lookup_node(state: QueryGraphState) -> dict:
    # Deduction/rebate limits, same authoritative-table basis as rate_lookup.
    card = build_deduction_card(state["as_of"], state["query"])
    return {"deduction_card": card, "gate_status": "VERIFIED", "gated_citations": []}


async def _computation_node(state: QueryGraphState) -> dict:
    trace = compute(_PERSONAL_RULE, state["extracted_inputs"], state["as_of"])
    return {
        "computation_trace": trace.model_dump(mode="json"),
        "computation_result": trace.outputs,
    }


async def _retrieval_node(state: QueryGraphState) -> dict:
    chunks = await hybrid_search(state["query"], state["as_of"])
    return {"retrieved_chunks": [c.model_dump() for c in chunks]}


async def _narrate_node(state: QueryGraphState) -> dict:
    system_prompt, messages = build_narration_messages(
        query=state["query"],
        chunks=state.get("retrieved_chunks") or [],
        computation=(state.get("computation_trace") or {}).get("outputs"),
        assumptions=state.get("assumptions"),
    )

    try:
        response = await generate_narrative(system_prompt, messages)
    except Exception as exc:
        # The LLM writes the prose; it does not produce the figures. Losing it
        # must not lose an answer that has already been computed exactly --
        # assemble_response falls back to rendering the trace directly. A 500
        # here would discard correct arithmetic because the narration failed,
        # which is the tail wagging the dog.
        #
        # Not silent: the response carries a note so the reader knows the
        # explanation is missing rather than assuming there was nothing to say.
        logger.warning("narration failed, answering from the computation: %s", exc)
        note = "The written explanation could not be generated; the figures below are unaffected."
        return {
            "llm_response": None,
            "assumptions": [*(state.get("assumptions") or []), note],
        }

    answer, citations = parse_narration(response.text)

    return {
        "llm_response": {
            "answer": answer,
            "citations": citations,
            "model_version": response.model_version,
            "provider_name": response.provider_name,
        }
    }


async def _evidence_gate_node(state: QueryGraphState) -> dict:
    llm_response = state.get("llm_response") or {}
    chunks = [RetrievedChunk(**c) for c in state.get("retrieved_chunks") or []]

    verified, gate_status = verify_citations(llm_response.get("citations") or [], chunks)

    # A BOTH query already collected graph-derived citations for its
    # computation. Those are verified by construction and must survive
    # alongside the gated narration citations, not be replaced by them.
    existing = [
        c for c in state.get("gated_citations") or [] if c.chunk_id not in {v.chunk_id for v in verified}
    ]

    return {"gated_citations": existing + verified, "gate_status": gate_status}


def _route_after_temporal(state: QueryGraphState) -> str:
    if state.get("missing"):
        return "clarify"
    if state["intent"] == Intent.RATE_LOOKUP:
        return "rate_lookup"
    if state["intent"] == Intent.DEDUCTION_LOOKUP:
        return "deduction_lookup"
    if state["intent"] == Intent.RETRIEVAL:
        return "retrieval"
    return "computation"


def _route_after_citations(state: QueryGraphState) -> str:
    return "retrieval" if state["intent"] == Intent.BOTH else "assemble_response"


def build_query_graph():
    graph = StateGraph(QueryGraphState)
    graph.add_node("classify_intent", _classify_intent_node)
    graph.add_node("extract_inputs", _extract_inputs_node)
    graph.add_node("resolve_temporal", _resolve_temporal_node)
    graph.add_node("clarify", _clarify_node)
    graph.add_node("rate_lookup", _rate_lookup_node)
    graph.add_node("deduction_lookup", _deduction_lookup_node)
    graph.add_node("computation", _computation_node)
    graph.add_node("computation_citations", resolve_computation_citations)
    graph.add_node("retrieval", _retrieval_node)
    graph.add_node("narrate", _narrate_node)
    graph.add_node("evidence_gate", _evidence_gate_node)
    graph.add_node("assemble_response", assemble_response)
    graph.add_node("audit_log", write_audit_log)

    graph.add_edge(START, "classify_intent")
    graph.add_edge("classify_intent", "extract_inputs")
    graph.add_edge("extract_inputs", "resolve_temporal")

    graph.add_conditional_edges(
        "resolve_temporal",
        _route_after_temporal,
        {
            "clarify": "clarify",
            "rate_lookup": "rate_lookup",
            "deduction_lookup": "deduction_lookup",
            "computation": "computation",
            "retrieval": "retrieval",
        },
    )

    graph.add_edge("clarify", "assemble_response")
    graph.add_edge("rate_lookup", "assemble_response")
    graph.add_edge("deduction_lookup", "assemble_response")
    graph.add_edge("computation", "computation_citations")
    graph.add_conditional_edges(
        "computation_citations",
        _route_after_citations,
        {"retrieval": "retrieval", "assemble_response": "assemble_response"},
    )
    graph.add_edge("retrieval", "narrate")
    graph.add_edge("narrate", "evidence_gate")
    graph.add_edge("evidence_gate", "assemble_response")
    graph.add_edge("assemble_response", "audit_log")
    graph.add_edge("audit_log", END)

    return graph.compile()


# Built once at import time -- building/compiling the graph only wires node
# names and edges together, it does not invoke any node body.
_compiled_graph = build_query_graph()


async def run_query_graph(domain: str, request: Any, user_id: str) -> dict:
    initial_state: QueryGraphState = {
        "query": request.query,
        "domain": domain,
        "user_id": user_id,
        "session_id": getattr(request, "session_id", None),
        "explicit_as_of_date": getattr(request, "as_of_date", None),
    }

    final_state = await _compiled_graph.ainvoke(initial_state)

    response = dict(final_state["final_response"])
    response["audit_log_id"] = (final_state.get("audit_entry") or {}).get("id") or ""
    return response
