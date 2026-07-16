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
    # Structured computation payload the caller supplies explicitly (form
    # input), e.g. {"rule_name": "capital_gains", "inputs": {...}} -- bypasses
    # free-text parsing entirely, since a pure rule function can never guess
    # a sourced number out of a sentence. Takes priority over `intent` for
    # routing when present.
    computation_request: dict[str, Any] | None
    # Raw text of a document the user uploaded with this query (e.g. a sale
    # deed), if any.
    uploaded_document_text: str | None
    intent: Intent
    as_of: TaxYearContext
    # LLM-extracted, evidence-span-verified fields from uploaded_document_text
    # (services.rag.extraction.document_extraction) -- only verified fields
    # ever reach `computation_request`'s inputs.
    extracted_inputs: dict[str, Any]
    extraction_missing_fields: list[str]
    computation_result: dict[str, Any] | None
    retrieved_chunks: list[dict[str, Any]]
    # Structured rate rules read from the Neo4j graph DB
    # (services.rag.retriever.graph_store) for the ground-truth check.
    graph_rules: list[dict[str, Any]]
    ground_truth_check: dict[str, Any] | None
    llm_response: dict[str, Any] | None
    gated_citations: list[Citation]
    gate_status: str
    final_response: dict[str, Any]
    audit_entry: dict[str, Any]
