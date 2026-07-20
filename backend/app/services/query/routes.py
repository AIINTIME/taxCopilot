"""POST /api/v1/{domain}/query -- the single entrypoint into the AI/RAG +
computation architecture. Reuses the existing auth dependency
(app.api.auth.get_current_user) for request attribution; delegates all actual
work to the LangGraph query graph in orchestration/.

POST /api/v1/{domain}/query/with-document is the same entrypoint plus a
user-attached file: text is extracted server-side (reusing the same
pdf_parser/docx_parser already proven by ingestion and analyze-return) and
fed into the graph as `uploaded_document_text`, on any domain -- not just
personal-tax's separate, unrelated analyze-return pipeline.
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.core.rbac import require_query_permission
from app.orchestration.graphs.query_graph import run_query_graph
from app.services.ingestion.parsing.docx_parser import parse_docx
from app.services.ingestion.parsing.pdf_parser import parse_pdf
from app.services.query.llm_query_understanding import QueryUnderstandingError
from app.shared.schemas.citation import Citation

router = APIRouter(prefix="/api/v1", tags=["query"])

# The workflows the client offers (see client/src/constants/workflows.ts).
# `domain` was previously an unvalidated str: /api/v1/banana/query returned 200
# and ran the identical pipeline. It still selects nothing -- no node reads it,
# retrieval is hardcoded to the statutory-kg namespace -- so this rejects a
# typo'd or invented domain at the door rather than pretending to honour it.
ALLOWED_DOMAINS = frozenset(
    {"personal-tax", "corporate-tax", "capital-gains", "notices"}
)

_TEXT_EXTENSIONS = (".txt", ".csv")


def _reject_unknown_domain(domain: str) -> None:
    """Both query entrypoints run the identical pipeline, so both validate the
    domain -- otherwise the with-document route is an unguarded way in.
    """
    if domain not in ALLOWED_DOMAINS:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown domain '{domain}'. Available domains: "
                f"{', '.join(sorted(ALLOWED_DOMAINS))}."
            ),
        )


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

    # Slab-rate table for a "what are the rates for AY X?" question, read from
    # slab_tables (never the LLM). None for every other query type.
    rate_card: dict | None = None

    # Deduction/rebate limit table for a "what is the 80D limit?" question,
    # also read from slab_tables. None for every other query type.
    deduction_card: dict | None = None


@router.post("/{domain}/query", response_model=QueryResponse)
async def query(
    domain: str,
    payload: QueryRequest,
    request: Request,
    user=Depends(get_current_user),
):
    # Rejected before the permission check: an invented domain is a 404, not a
    # 403 -- asking whether the user may query "banana" implies it exists.
    _reject_unknown_domain(domain)
    await require_query_permission(domain, user, request)
    try:
        return await run_query_graph(domain=domain, request=payload, user_id=user.id)
    except QueryUnderstandingError:
        # The LLM is the sole intent classifier (no regex/embedding
        # fallback) -- a failed classification call is a real failure, not
        # something to paper over with a weaker guess, so it surfaces here as
        # an honest, retry-able error rather than a 200 with a wrong answer.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Something went wrong understanding your question. Please try again.",
        ) from None


def _extract_document_text(filename: str, content: bytes) -> str:
    lower_name = filename.lower()
    if lower_name.endswith(".pdf"):
        return parse_pdf(content)
    if lower_name.endswith(".docx"):
        return parse_docx(content)
    if lower_name.endswith(_TEXT_EXTENSIONS):
        return content.decode("utf-8", errors="replace")

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Unsupported file type for {filename!r} -- attach a PDF, DOCX, "
            "TXT, or CSV file."
        ),
    )


@router.post("/{domain}/query/with-document", response_model=QueryResponse)
async def query_with_document(
    domain: str,
    request: Request,
    file: UploadFile,
    query: str = Form(...),
    as_of_date: date | None = Form(default=None),
    session_id: str | None = Form(default=None),
    user=Depends(get_current_user),
):
    _reject_unknown_domain(domain)
    await require_query_permission(domain, user, request)

    content = await file.read()
    document_text = _extract_document_text(file.filename or "", content)

    payload = QueryRequest(
        query=query,
        as_of_date=as_of_date,
        session_id=session_id,
        uploaded_document_text=document_text,
    )

    try:
        return await run_query_graph(domain=domain, request=payload, user_id=user.id)
    except QueryUnderstandingError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Something went wrong understanding your question. Please try again.",
        ) from None
