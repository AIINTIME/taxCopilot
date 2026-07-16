"""POST /api/v1/personal-tax/analyze-return -- upload a filed return, get back
the discrepancies with the line each one came from, plus the AI score.

This is the read side of services/analysis: it runs the already-tested pipeline
(extract -> reconcile -> score) over an uploaded file. No detection logic lives
here; the route is wiring, the same way services/query/routes.py is wiring over
the graph.

Penalties and verdicts are intentionally absent from the output for now: they
come from the Neo4j rule graph (penalty_mapper), which is empty/unavailable, so
`penalties` is always [] here. Detection and "where it went wrong" do not depend
on the graph and work today.
"""

from typing import Any

from fastapi import APIRouter, Depends, Form, UploadFile
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.services.analysis.ai_score import AIScore, score_return
from app.services.analysis.itr_extractor import ExtractedReturn, extract_from_text
from app.services.analysis.reconciler import (
    Discrepancy,
    ReconciliationResult,
    reconcile,
)
from app.services.computation.rules.personal.deduction_sections import SECTION_LABELS
from app.services.ingestion.parsing.pdf_parser import parse_pdf
from app.services.query.temporal_resolver import resolve_as_of

router = APIRouter(prefix="/api/v1/personal-tax", tags=["analysis"])

# Discrepancy.section_reference is a LABEL ("Sec 80C"); provenance is keyed by
# FIELD ("section_80c"). Invert the vocabulary so a finding can be traced back
# to the line it came from. The two non-section discrepancy kinds map to their
# own provenance fields.
_LABEL_TO_FIELD = {label: field for field, label in SECTION_LABELS.items()}
_TAX_MISMATCH_FIELD = "declared_tax"
_REGIME_FIELD = "regime_filed"


class DiscrepancyOut(BaseModel):
    type: str
    severity: str
    section_reference: str | None
    summary: str
    declared: float | None
    correct: float | None
    cost: float | None
    source_line: str | None
    """The verbatim line in the uploaded return this finding refers to -- the
    "where it went wrong". None when the figure was computed rather than read
    (e.g. the recommended-regime comparison).
    """


class ScoreOut(BaseModel):
    accuracy: float
    risk: float
    grade: str
    overall: float
    findings: int
    exposure: float
    explanation: list[str]


class AnalyzeReturnResponse(BaseModel):
    usable: bool
    missing: list[str]
    clarification: str | None
    declared: dict[str, Any]
    discrepancies: list[DiscrepancyOut]
    score: ScoreOut | None
    penalties: list[dict] = []
    as_of_date: str


def _source_line(discrepancy: Discrepancy, provenance: dict[str, str]) -> str | None:
    from app.services.analysis.reconciler import DiscrepancyType

    if discrepancy.type is DiscrepancyType.TAX_MISMATCH:
        return provenance.get(_TAX_MISMATCH_FIELD)
    if discrepancy.type is DiscrepancyType.SUBOPTIMAL_REGIME:
        return provenance.get(_REGIME_FIELD)

    field = _LABEL_TO_FIELD.get(discrepancy.section_reference or "")
    return provenance.get(field) if field else None


def _to_score_out(score: AIScore) -> ScoreOut:
    return ScoreOut(
        accuracy=score.accuracy,
        risk=score.risk,
        grade=score.grade.value,
        overall=score.overall,
        findings=score.findings,
        exposure=score.exposure,
        explanation=list(score.explanation),
    )


def _declared_summary(extracted: ExtractedReturn) -> dict[str, Any]:
    if extracted.filed is None:
        return {}
    filed = extracted.filed
    return {
        "gross_income": filed.gross_income,
        "income_type": filed.income_type.value,
        "regime_filed": filed.regime_filed.value,
        "declared_tax": filed.declared_tax,
        "deductions": {
            f.name: getattr(filed.deductions, f.name)
            for f in filed.deductions.__dataclass_fields__.values()
            if getattr(filed.deductions, f.name)
        },
        "provenance": filed.provenance,
    }


def analyze_return_text(
    text: str, assessment_year: str | None = None
) -> AnalyzeReturnResponse:
    """Core pipeline, separated from the HTTP layer so it is unit-testable
    without constructing a PDF. The route is just parse_pdf + this.
    """
    # Resolve an as-of context. itr_extractor does not read the AY from the
    # return yet, so honour an explicit override, else default to the most
    # recently completed FY (the year most returns on hand are for).
    query = f"assessment year {assessment_year}" if assessment_year else ""
    as_of = resolve_as_of(query)

    extracted = extract_from_text(text)

    if not extracted.is_usable:
        # Conservative by design: an ambiguous regime or a missing income is
        # reported, not guessed. Mirror the query flow -- a clarification, not
        # a 500 or a confidently wrong analysis.
        return AnalyzeReturnResponse(
            usable=False,
            missing=list(extracted.missing),
            clarification=(
                "I could not read "
                + ", ".join(extracted.missing)
                + " from this document. Please confirm these so I can analyse the return."
            ),
            declared=_declared_summary(extracted),
            discrepancies=[],
            score=None,
            penalties=[],
            as_of_date=as_of.as_of_date.isoformat(),
        )

    result: ReconciliationResult = reconcile(extracted.filed, as_of)
    score = score_return(result)
    provenance = extracted.filed.provenance

    return AnalyzeReturnResponse(
        usable=True,
        missing=[],
        clarification=None,
        declared=_declared_summary(extracted),
        discrepancies=[
            DiscrepancyOut(
                type=d.type.value,
                severity=d.severity.value,
                section_reference=d.section_reference,
                summary=d.summary,
                declared=d.declared,
                correct=d.correct,
                cost=d.cost,
                source_line=_source_line(d, provenance),
            )
            for d in result.discrepancies
        ],
        score=_to_score_out(score),
        penalties=[],  # graph-sourced; empty until Phase 4
        as_of_date=as_of.as_of_date.isoformat(),
    )


@router.post("/analyze-return", response_model=AnalyzeReturnResponse)
async def analyze_return(
    file: UploadFile,
    assessment_year: str | None = Form(default=None),
    user=Depends(get_current_user),
):
    content = await file.read()
    text = parse_pdf(content)
    return analyze_return_text(text, assessment_year)
