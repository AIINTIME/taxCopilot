"""Shared LangGraph state schema threaded across every node in query_graph.py.

Deliberately decoupled from services/query/routes.py's QueryRequest/
QueryResponse -- the graph is driven by plain arguments (see
run_query_graph in graphs/query_graph.py) so orchestration never depends on
the FastAPI request/response schema, and routes.py never has to import from
orchestration/graphs/query_graph.py's internals beyond run_query_graph itself.
"""

from datetime import date
from typing import Any, TypedDict

from app.services.query.intent_classifier import Intent
from app.shared.schemas.citation import Citation
from app.shared.schemas.tax_year import TaxYearContext


class QueryGraphState(TypedDict, total=False):
    query: str
    domain: str
    user_id: str
    session_id: str | None
    explicit_as_of_date: date | None
    intent: Intent
    as_of: TaxYearContext
    computation_result: dict[str, Any] | None
    retrieved_chunks: list[dict[str, Any]]
    llm_response: dict[str, Any] | None
    gated_citations: list[Citation]
    gate_status: str
    final_response: dict[str, Any]
    audit_entry: dict[str, Any]
