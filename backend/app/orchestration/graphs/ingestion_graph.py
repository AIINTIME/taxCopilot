"""LangGraph StateGraph for the ingestion pipeline: fetch (scrape or upload)
-> parse -> dedup -> embed -> upsert. Node functions are thin wrappers around
services.ingestion.* -- no business logic in this file itself.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.services.ingestion.dedup import content_hash, has_changed
from app.services.ingestion.embedding import embed_texts
from app.services.ingestion.parsing.pdf_parser import parse_pdf
from app.services.ingestion.parsing.xlsx_parser import parse_xlsx
from app.services.ingestion.upsert.statutory_kg_upsert import upsert_provision
from app.services.ingestion.upsert.user_docs_upsert import upsert_session_document


class IngestionGraphState(TypedDict, total=False):
    source_id: str
    session_id: str | None
    raw_content: bytes
    content_type: str
    existing_hash: str | None
    parsed_text: str
    embeddings: list[list[float]]
    upserted_id: str


async def _parse_node(state: IngestionGraphState) -> dict:
    raise NotImplementedError(
        "TODO: dispatch to parse_pdf/parse_xlsx based on "
        "state['content_type'] and set 'parsed_text'"
    )


async def _dedup_node(state: IngestionGraphState) -> dict:
    new_hash = content_hash(state["raw_content"])
    if not has_changed(new_hash, state.get("existing_hash")):
        raise NotImplementedError(
            "TODO: short-circuit the graph when content is unchanged"
        )
    return {}


async def _embed_node(state: IngestionGraphState) -> dict:
    raise NotImplementedError(
        "TODO: call embed_texts on chunks of state['parsed_text'] once an "
        "embedding provider is wired (see services/ingestion/embedding.py)"
    )


async def _upsert_node(state: IngestionGraphState) -> dict:
    raise NotImplementedError(
        "TODO: route to upsert_provision (statutory KG) or "
        "upsert_session_document (session_id set) based on state"
    )


def build_ingestion_graph():
    graph = StateGraph(IngestionGraphState)
    graph.add_node("dedup", _dedup_node)
    graph.add_node("parse", _parse_node)
    graph.add_node("embed", _embed_node)
    graph.add_node("upsert", _upsert_node)

    graph.add_edge(START, "dedup")
    graph.add_edge("dedup", "parse")
    graph.add_edge("parse", "embed")
    graph.add_edge("embed", "upsert")
    graph.add_edge("upsert", END)

    return graph.compile()


_compiled_ingestion_graph = build_ingestion_graph()


async def run_ingestion_graph(initial_state: IngestionGraphState) -> IngestionGraphState:
    return await _compiled_ingestion_graph.ainvoke(initial_state)
