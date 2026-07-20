"""Shared LangGraph state schema threaded across every node in query_graph.py.

Deliberately decoupled from services/query/routes.py's QueryRequest/
QueryResponse -- the graph is driven by plain arguments (see
run_query_graph in graphs/query_graph.py) so orchestration never depends on
the FastAPI request/response schema, and routes.py never has to import from
orchestration/graphs/query_graph.py's internals beyond run_query_graph itself.
"""

from datetime import date
from typing import Any, TypedDict

from app.services.query.intent_classifier_types import Intent
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
    # Structured financial figures for a computation-intent query where no
    # computation_request/document was supplied -- paired with the rule name
    # the classify_intent node's LLM call identified (services.query.
    # llm_query_understanding).
    computation_inputs: dict[str, Any] | None
    intent: Intent
    # Rule name from services.query.llm_query_understanding's LLM call
    # (classify_intent node) -- consumed directly by _computation_node. There
    # is no deterministic fallback: a failed LLM call raises
    # QueryUnderstandingError and aborts the graph before _computation_node
    # runs, so this key is always present by the time it's read. None is a
    # legitimate value meaning the LLM could not confidently identify a rule.
    rule_name: str | None
    as_of: TaxYearContext
    # LLM-extracted, evidence-span-verified fields from uploaded_document_text
    # (services.rag.extraction.document_extraction) -- only verified fields
    # ever reach `computation_request`'s inputs.
    extracted_inputs: dict[str, Any]
    extraction_missing_fields: list[str]
    # LLM-proposed, evidence-span-verified computation inputs parsed from the
    # query text itself, e.g. "my salary is 21 lakhs" -> {"gross_income":
    # 2100000, ...} (services.query.llm_query_understanding). Distinct from
    # `extracted_inputs` above, which comes from an uploaded document rather
    # than the query text. Every number here was re-derived deterministically
    # from a verified span, never taken as the LLM's own stated value -- see
    # llm_query_understanding.py. `assumptions` surfaces what was inferred
    # (e.g. an unstated income type defaulted to salaried) so the narration/
    # response can disclose it rather than silently assume it.
    parsed_query_inputs: dict[str, Any]
    # Required fields llm_query_understanding could not fill -- mirrors
    # ExtractedInputs.missing. Non-empty means parsed_query_inputs is not yet
    # usable and the caller must ask for clarification instead of computing
    # on it.
    parsed_query_missing_fields: list[str]
    assumptions: list[str]
    computation_result: dict[str, Any] | None

    # Set when the question is one this system cannot honestly source at all --
    # an indirect tax, a "what changed this week", a 2025-Act comparison. The
    # graph short-circuits to the response rather than retrieving. See
    # services/query/scope_guard.py.
    scope_decline: dict[str, Any] | None

    # Rate-table lookup ("what are the slab rates for AY X?") -- read from
    # slab_tables, never the LLM. See services/query/rate_lookup.py.
    rate_card: dict[str, Any] | None

    # Deduction/rebate limit lookup ("what is the 80D limit?") -- also from
    # slab_tables, same reason.
    deduction_card: dict[str, Any] | None

    # Sections the computation trace cited that the rule graph could not
    # resolve to a source (orchestration.nodes.computation_citations).
    # Surfaced on the response so an answer with no citations is visibly
    # uncited rather than silently so.
    uncited_sections: list[str]

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
