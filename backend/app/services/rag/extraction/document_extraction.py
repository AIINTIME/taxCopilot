"""Query-time extraction of structured capital-gains figures from a user's
uploaded document (e.g. a sale deed or broker contract note).

Same pattern as
services/ingestion/kg_graph_extraction/rule_proposal.py's statutory-rule
extraction: the LLM proposes field values, but every field must carry a
verbatim evidence span re-verified programmatically against the source text
before it's trusted (`_verify_evidence_span`). A field that fails
verification -- or was never proposed -- is never passed into
CapitalGainsInput; the caller (orchestration's computation node) must treat
a query with any unverified required field as needing user confirmation,
never as a silent estimate. This mirrors the "no estimated figures" rule
(services/computation/validators.py) at the intake boundary instead of
inside the pure computation core.

This is deliberately query-time and per-user, unlike
services/ingestion/kg_graph_extraction/ which builds the *permanent*
statutory knowledge graph from admin-uploaded sources -- the two are kept
separate. This module calls services.rag.llm_client.generate_narrative
(never imports shared/llm directly), preserving the rule that llm_client.py
is the only file under services/ allowed to do so.
"""

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.services.rag.llm_client import generate_narrative
from app.services.rag.prompts.extraction_prompts import (
    CAPITAL_GAINS_EXTRACTION_SYSTEM_PROMPT,
)
from app.shared.llm.base import LLMMessage

REQUIRED_CAPITAL_GAINS_FIELDS = (
    "asset_class",
    "acquisition_date",
    "transfer_date",
    "full_value_consideration",
    "cost_of_acquisition",
)
_DATE_FIELDS = {"acquisition_date", "transfer_date"}
_OPTIONAL_FIELDS = ("cost_of_improvement",)


@dataclass(frozen=True)
class ExtractedField:
    value: Any
    evidence_span: str | None
    verified: bool


def _verify_evidence_span(evidence_span: str | None, source_text: str) -> bool:
    if not evidence_span or not evidence_span.strip():
        return False
    return evidence_span.lower() in source_text.lower()


async def extract_capital_gains_inputs(document_text: str) -> dict[str, ExtractedField]:
    response = await generate_narrative(
        system_prompt=CAPITAL_GAINS_EXTRACTION_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=document_text)],
    )

    try:
        data = json.loads(response.text.strip())
    except (json.JSONDecodeError, AttributeError):
        return {}

    fields = data.get("fields") if isinstance(data, dict) else None
    if not isinstance(fields, dict):
        return {}

    extracted: dict[str, ExtractedField] = {}
    for name, field_data in fields.items():
        if not isinstance(field_data, dict):
            continue
        value = field_data.get("value")
        evidence_span = field_data.get("evidence_span")
        verified = _verify_evidence_span(evidence_span, document_text) and value is not None

        if verified and name in _DATE_FIELDS:
            try:
                value = date.fromisoformat(str(value))
            except ValueError:
                verified = False

        extracted[name] = ExtractedField(value=value, evidence_span=evidence_span, verified=verified)

    return extracted


def verified_fields_to_computation_inputs(
    extracted: dict[str, ExtractedField],
) -> tuple[dict[str, Any], list[str]]:
    """Split extracted fields into (usable computation inputs, missing/unverified
    required field names). Never includes an unverified field's value -- a
    non-empty `missing` list means the caller must ask the user to confirm
    or supply those fields directly rather than computing anything.
    """
    inputs: dict[str, Any] = {}
    missing: list[str] = []

    for field_name in REQUIRED_CAPITAL_GAINS_FIELDS:
        extracted_field = extracted.get(field_name)
        if extracted_field is not None and extracted_field.verified:
            inputs[field_name] = extracted_field.value
        else:
            missing.append(field_name)

    for field_name in _OPTIONAL_FIELDS:
        extracted_field = extracted.get(field_name)
        if extracted_field is not None and extracted_field.verified:
            inputs[field_name] = extracted_field.value

    return inputs, missing
