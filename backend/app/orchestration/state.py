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

    # Deterministically extracted computation inputs. `missing` non-empty means
    # a required fact was absent and the graph must ask rather than guess --
    # computing exactly on an invented input is the worst outcome available.
    extracted_inputs: dict[str, Any]
    assumptions: list[str]
    missing: list[str]
    clarification: str | None

    computation_result: dict[str, Any] | None
    computation_trace: dict[str, Any] | None

    # Sections the computation trace cited that the rule graph could not
    # resolve to a source. Surfaced on the response so an answer with no
    # citations is visibly uncited rather than silently so.
    uncited_sections: list[str]

    retrieved_chunks: list[dict[str, Any]]
    llm_response: dict[str, Any] | None
    gated_citations: list[Citation]
    gate_status: str
    final_response: dict[str, Any]
    audit_entry: dict[str, Any]
