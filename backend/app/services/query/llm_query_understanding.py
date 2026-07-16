"""LLM-first intent classification and personal-tax field extraction from a
user's free-text query.

The LLM proposes intent, rule_name, and (for personal_regime_comparison)
candidate field values with verbatim evidence spans. Routing (intent,
rule_name) is trusted directly from the LLM -- a wrong route already degrades
safely today (a `missing_data` clarification prompt or a retrieval answer),
never a wrong computed figure. Numbers are not: every proposed amount is
re-derived from its verified evidence span via the existing, unit-tested
`input_extractor.parse_amount`, never taken as the LLM's own stated value --
this is one step stricter than services/rag/extraction/document_extraction.py,
which verifies the span exists but still trusts the LLM's own `value`. Here,
the LLM's `value` is discarded entirely once a field is deemed relevant; the
number that reaches the computation engine always comes from re-parsing the
matched source text, never from LLM arithmetic.

This is the ONLY classification mechanism -- there is deliberately no regex/
embedding fallback. A failure here (API outage, malformed response, an
intent/rule_name outside the known vocabulary) is a real failure, not
something to silently paper over with a weaker classifier: it is re-raised by
orchestration/graphs/query_graph.py's classify_intent node as
QueryUnderstandingError, aborts the graph, and surfaces at the API layer
(services/query/routes.py) as a clear, retry-able error to the caller.
"""

import json
from dataclasses import dataclass

from app.services.computation.engine import RULES
from app.services.computation.rules.personal.deduction_sections import (
    SECTION_LABELS,
    SECTION_PATTERNS,
)
from app.services.computation.rules.personal.regime_comparison_personal import IncomeType
from app.services.query.input_extractor import ExtractedInputs, detect_income_type, parse_amount
from app.services.query.intent_classifier_types import Intent
from app.services.rag.llm_client import generate_narrative
from app.services.rag.prompts.query_understanding_prompts import QUERY_UNDERSTANDING_SYSTEM_PROMPT
from app.shared.llm.base import LLMMessage

__all__ = ["QueryUnderstanding", "QueryUnderstandingError", "classify_and_extract"]

_AMOUNT_FIELDS = ("gross_income", *SECTION_LABELS)


class QueryUnderstandingError(Exception):
    """Raised whenever the LLM's response cannot be trusted for routing --
    malformed JSON, an unknown intent/rule_name, or any other shape the
    caller did not ask for. The caller is expected to fall back to the
    deterministic pipeline, never to guess at a partial result."""


@dataclass(frozen=True)
class QueryUnderstanding:
    intent: Intent
    rule_name: str | None
    extracted: ExtractedInputs | None


def _verify_evidence_span(evidence_span: str | None, query: str) -> bool:
    if not evidence_span or not evidence_span.strip():
        return False
    return evidence_span.lower() in query.lower()


def _strip_markdown_fence(text: str) -> str:
    """The prompt asks for raw JSON, no fences -- observed in practice not to
    be reliably followed (a ```json ... ``` block came back despite the
    instruction), so this is stripped defensively rather than trusted."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = stripped.removeprefix("```json").removeprefix("```").strip()
    return stripped.removesuffix("```").strip()


def _parse_response(raw_text: str) -> dict:
    try:
        data = json.loads(_strip_markdown_fence(raw_text))
    except (json.JSONDecodeError, AttributeError) as exc:
        raise QueryUnderstandingError(f"non-JSON response: {raw_text!r}") from exc
    if not isinstance(data, dict):
        raise QueryUnderstandingError(f"response is not a JSON object: {raw_text!r}")
    return data


def _parse_intent(data: dict) -> Intent:
    try:
        return Intent(data.get("intent"))
    except ValueError as exc:
        raise QueryUnderstandingError(f"unknown intent: {data.get('intent')!r}") from exc


def _parse_rule_name(data: dict) -> str | None:
    rule_name = data.get("rule_name")
    if rule_name is None:
        return None
    if rule_name not in RULES:
        raise QueryUnderstandingError(f"unknown rule_name: {rule_name!r}")
    return rule_name


def _extract_amount_field(
    field_name: str, field_data: object, query: str
) -> tuple[float, str] | None:
    """Returns (re-derived value, evidence_span text) if the field is present
    and its evidence_span both verifies against the query and, for a
    deduction section, actually matches that section's own pattern -- or
    None if the field should be dropped. The LLM's own numeric `value` is
    never read past this point; parse_amount(evidence_span) is the number
    that reaches the computation engine."""
    if not isinstance(field_data, dict):
        return None
    evidence_span = field_data.get("evidence_span")
    if not isinstance(evidence_span, str) or not _verify_evidence_span(evidence_span, query):
        return None

    section_pattern = SECTION_PATTERNS.get(field_name)
    if section_pattern is not None and not section_pattern.search(evidence_span):
        return None

    value = parse_amount(evidence_span)
    if value is None or value <= 0:
        return None
    return value, evidence_span


def _extract_income_type(field_data: object, query: str) -> IncomeType | None:
    if not isinstance(field_data, dict):
        return None
    evidence_span = field_data.get("evidence_span")
    if not isinstance(evidence_span, str) or not _verify_evidence_span(evidence_span, query):
        return None
    return detect_income_type(evidence_span)


def _extract_inputs_from_fields(fields: object, query: str) -> ExtractedInputs:
    if not isinstance(fields, dict):
        fields = {}

    values: dict[str, float] = {}
    deductions: dict[str, float] = {}
    provenance: dict[str, str] = {}
    assumptions: list[str] = []
    missing: list[str] = []

    income = _extract_amount_field("gross_income", fields.get("gross_income"), query)
    if income is None:
        missing.append("gross_income")
    else:
        values["gross_income"], provenance["gross_income"] = income

    income_type = _extract_income_type(fields.get("income_type"), query)
    if income_type is None:
        missing.append("income_type")
    else:
        provenance["income_type"] = income_type.value

    for field_name in SECTION_LABELS:
        deduction = _extract_amount_field(field_name, fields.get(field_name), query)
        if deduction is not None:
            deductions[field_name], provenance[field_name] = deduction

    if not deductions and income_type is not None:
        assumptions.append(
            "No deductions (80C/80D/HRA) were read from your question, so none were applied"
        )

    return ExtractedInputs(
        values=values,
        income_type=income_type,
        deductions=deductions,
        assumptions=tuple(assumptions),
        missing=tuple(missing),
        provenance=provenance,
    )


async def classify_and_extract(query: str) -> QueryUnderstanding:
    """The sole intent classification + extraction call -- no deterministic
    fallback. Raises QueryUnderstandingError on any response the caller
    should not trust; the caller must let that propagate as a real failure,
    never swallow it into a default/guessed classification."""
    response = await generate_narrative(
        system_prompt=QUERY_UNDERSTANDING_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=query)],
    )
    data = _parse_response(response.text)

    intent = _parse_intent(data)
    rule_name = _parse_rule_name(data)

    extracted: ExtractedInputs | None = None
    if rule_name == "personal_regime_comparison":
        extracted = _extract_inputs_from_fields(data.get("fields"), query)

    return QueryUnderstanding(intent=intent, rule_name=rule_name, extracted=extracted)
