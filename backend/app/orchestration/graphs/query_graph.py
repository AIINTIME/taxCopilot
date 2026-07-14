"""The actual LangGraph implementation wiring the full query flow:

    intent classify -> temporal resolve
        -> (computation engine | hybrid retriever -> llm_client -> evidence gate)
        -> assemble_response -> audit_log_node

Node functions here are thin wrappers that call straight into services/* --
this file contains no business logic itself, only graph wiring and state
plumbing, per the orchestration-layer rule.
"""

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.orchestration.nodes.assemble_response import assemble_response
from app.orchestration.nodes.audit_log_node import write_audit_log
from app.orchestration.state import QueryGraphState
from app.services.computation.engine import compute
from app.services.query.intent_classifier import Intent, classify_intent
from app.services.query.temporal_resolver import resolve_as_of
from app.services.rag.evidence_gate import verify_citations
from app.services.rag.llm_client import generate_narrative
from app.services.rag.retriever.hybrid_retriever import hybrid_search


async def _classify_intent_node(state: QueryGraphState) -> dict:
    return {"intent": classify_intent(state["query"])}


async def _resolve_temporal_node(state: QueryGraphState) -> dict:
    as_of = resolve_as_of(state["query"], state.get("explicit_as_of_date"))
    return {"as_of": as_of}


async def _computation_node(state: QueryGraphState) -> dict:
    raise NotImplementedError(
        "TODO: derive rule_name + inputs from state['query']/session context "
        "and call services.computation.engine.compute(...)"
    )


async def _retrieval_node(state: QueryGraphState) -> dict:
    chunks = await hybrid_search(state["query"], state["as_of"])
    return {"retrieved_chunks": [c.model_dump() for c in chunks]}


async def _narrate_node(state: QueryGraphState) -> dict:
    raise NotImplementedError(
        "TODO: build a system prompt (services.rag.prompts) + messages from "
        "state['retrieved_chunks'] and call "
        "services.rag.llm_client.generate_narrative(...)"
    )


async def _evidence_gate_node(state: QueryGraphState) -> dict:
    raise NotImplementedError(
        "TODO: extract citations from state['llm_response'] and call "
        "services.rag.evidence_gate.verify_citations(state['retrieved_chunks'])"
    )


def _route_after_temporal(state: QueryGraphState) -> str:
    # TODO: Intent.BOTH should traverse both branches; for now it is routed
    # through retrieval, same as Intent.RETRIEVAL, pending a fan-out design.
    if state["intent"] == Intent.COMPUTATION:
        return "computation"
    return "retrieval"


def build_query_graph():
    graph = StateGraph(QueryGraphState)
    graph.add_node("classify_intent", _classify_intent_node)
    graph.add_node("resolve_temporal", _resolve_temporal_node)
    graph.add_node("computation", _computation_node)
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
    graph.add_edge("computation", "assemble_response")
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
    raise NotImplementedError(
        "TODO: build the initial QueryGraphState from `request` (query, "
        "as_of_date, session_id), `domain`, and `user_id`, invoke "
        "_compiled_graph.ainvoke(initial_state), and return "
        "final_state['final_response']"
    )
