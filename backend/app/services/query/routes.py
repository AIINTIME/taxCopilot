"""POST /api/v1/{domain}/query -- the single entrypoint into the AI/RAG +
computation architecture. Reuses the existing auth dependency
(app.api.auth.get_current_user) for request attribution; delegates all actual
work to the LangGraph query graph in orchestration/.
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from fastapi import Request
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.core.rbac import require_query_permission
from app.orchestration.graphs.query_graph import run_query_graph
from app.shared.schemas.citation import Citation

router = APIRouter(prefix="/api/v1", tags=["query"])


class ComputationRequest(BaseModel):
    """Structured computation payload, e.g. {"rule_name": "capital_gains",
    "inputs": {...}} -- bypasses free-text parsing entirely, since a pure
    rule function can never guess a sourced number out of a sentence. See
    services/computation/engine.py's RULES for valid rule_name values and
    each rule's *Input dataclass for valid `inputs` keys.
    """

    rule_name: str
    inputs: dict[str, Any]


class QueryRequest(BaseModel):
    query: str
    as_of_date: date | None = None
    session_id: str | None = None
    computation_request: ComputationRequest | None = None
    # Raw text of a document the user uploaded with this query (e.g. a sale
    # deed) -- extracted fields are evidence-span verified against this text
    # before use (services/rag/extraction/document_extraction.py).
    uploaded_document_text: str | None = None
    # Structured financial figures for a computation-intent query where no
    # computation_request/document was supplied and the rule name is instead
    # inferred from the query text. If a computation query arrives without
    # the fields its rule needs, the response flags exactly what's missing
    # rather than assuming/defaulting.
    computation_inputs: dict[str, Any] | None = None


class QueryResponse(BaseModel):
    answer: str
    summary: str
    citations: list[Citation]
    computation_trace: dict | None = None
    ground_truth_check: dict | None = None
    gate_status: str
    as_of_date: date
    audit_log_id: str

    # Sections the computation trace cited that the rule graph could not
    # resolve to a source. A computation is VERIFIED because its figures come
    # from pure functions over versioned rate tables -- not because anything
    # was cited -- so this keeps "verified but unsourced" visible to the client
    # instead of silently returning an empty citations list.
    uncited_sections: list[str] = []

    # Facts the extractor inferred rather than being told, e.g. that no
    # deductions were claimed. Surfaced so the user can correct them: an
    # unstated deduction is the single most likely reason a regime
    # recommendation is right in arithmetic and wrong in practice.
    assumptions: list[str] = []

    # True when required inputs were missing and `answer` is a question rather
    # than an answer. The system asks instead of guessing -- computing exactly
    # on an invented input is worse than not computing.
    clarification_needed: bool = False


@router.post("/{domain}/query", response_model=QueryResponse)
async def query(
    domain: str,
    payload: QueryRequest,
    request: Request,
    user=Depends(get_current_user),
):
    await require_query_permission(domain, user, request)
    return await run_query_graph(domain=domain, request=payload, user_id=user.id)
