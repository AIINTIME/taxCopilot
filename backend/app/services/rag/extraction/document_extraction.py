"""Query-time extraction of structured computation figures from a user's
uploaded document (e.g. a sale deed, P&L statement, filed return, or broker
contract note) -- rule-aware: which fields get extracted depends on which
computation rule the query actually needs (`query_graph.py`'s
`_document_extraction_node` supplies the rule_name, already determined by
classify_intent before this runs).

Same pattern as
services/ingestion/kg_graph_extraction/rule_proposal.py's statutory-rule
extraction: the LLM proposes field values, but every field must carry a
verbatim evidence span re-verified programmatically against the source text
before it's trusted (`_verify_evidence_span`). A field that fails
verification -- or was never proposed -- is never passed into a rule's
Input dataclass; the caller (orchestration's computation node) must treat a
query with any unverified required field as needing user confirmation, never
as a silent estimate. This mirrors the "no estimated figures" rule
(services/computation/validators.py) at the intake boundary instead of
inside the pure computation core.

This is deliberately query-time and per-user, unlike
services/ingestion/kg_graph_extraction/ which builds the *permanent*
statutory knowledge graph from admin-uploaded sources -- the two are kept
separate. This module calls services.rag.llm_client.generate_narrative
(never imports shared/llm directly), preserving the rule that llm_client.py
is the only file under services/ allowed to do so.

`personal_regime_comparison` is deliberately NOT handled here -- see
services/query/llm_query_understanding.py's `extract_fields_from_text`,
which this module's caller (query_graph.py) uses directly against document
text for that one rule, reusing the exact same evidence-span + re-derived-
amount discipline already proven for the query-text extraction path, rather
than a second, divergent implementation of the same guarantee.
"""

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.services.rag.llm_client import generate_narrative
from app.services.rag.prompts.extraction_prompts import FieldSpec, build_extraction_prompt
from app.shared.llm.base import LLMMessage

# One field spec list per rule that engine.py dispatches via reflection
# (_INPUT_TYPES) -- mirrors each rule's *Input dataclass field-for-field so
# there is one place (not two) that has to change if a rule's inputs change.
# personal_regime_comparison is intentionally absent (see module docstring).
RULE_FIELD_SPECS: dict[str, list[FieldSpec]] = {
    "mat": [
        FieldSpec("book_profit", "number", True, description="book profit under Sec 115JB"),
        FieldSpec("normal_tax_payable", "number", True, description="tax payable under normal provisions"),
    ],
    "amt": [
        FieldSpec("adjusted_total_income", "number", True),
        FieldSpec("normal_tax_payable", "number", True),
    ],
    "regime_comparison": [
        FieldSpec("total_income", "number", True),
        FieldSpec(
            "is_new_manufacturing_company", "bool", False,
            description="whether this is a new manufacturing company eligible for Sec 115BAB",
        ),
    ],
    "depreciation": [
        FieldSpec("opening_wdv", "number", True, description="opening written-down value of the block"),
        FieldSpec("additions", "number", True),
        FieldSpec("disposals", "number", True),
        FieldSpec("block_rate", "number", True, description="depreciation block rate as a decimal, e.g. 0.15"),
    ],
    "capital_gains": [
        FieldSpec(
            "asset_class", "enum", True,
            enum_values=("listed_equity_or_equity_mf", "other"),
            description=(
                '"listed_equity_or_equity_mf" only if the document explicitly describes '
                "STT-paid listed equity shares, equity-oriented mutual fund units, or "
                'business trust units; otherwise "other"'
            ),
        ),
        FieldSpec("acquisition_date", "date", True),
        FieldSpec("transfer_date", "date", True),
        FieldSpec("full_value_consideration", "number", True),
        FieldSpec("cost_of_acquisition", "number", True),
        FieldSpec("cost_of_improvement", "number", False),
    ],
    "capital_gains_exemption": [
        FieldSpec("section", "enum", True, enum_values=("54", "54B", "54EC", "54F")),
        FieldSpec("capital_gain", "number", True),
        FieldSpec("cost_of_new_asset", "number", True),
        FieldSpec("investment_date", "date", True),
        FieldSpec("transfer_date", "date", True),
        FieldSpec(
            "net_consideration", "number", False,
            description="required for Sec 54F's proportionate formula",
        ),
        # Eligibility booleans (owns_more_than_one_other_residential_house,
        # land_used_for_agriculture_two_years_prior, etc.) are deliberately
        # not extracted -- a sale deed rarely states them explicitly, and
        # ExemptionInput's own defaults already encode the "assume eligible
        # unless told otherwise" stance the rule file documents. Guessing
        # them from a document risks a wrong exemption, not just a missing
        # one.
    ],
}

@dataclass(frozen=True)
class ExtractedField:
    value: Any
    evidence_span: str | None
    verified: bool


def _verify_evidence_span(evidence_span: str | None, source_text: str) -> bool:
    if not evidence_span or not evidence_span.strip():
        return False
    return evidence_span.lower() in source_text.lower()


async def extract_fields_for_rule(
    rule_name: str, document_text: str
) -> dict[str, ExtractedField]:
    field_specs = RULE_FIELD_SPECS.get(rule_name)
    if not field_specs:
        return {}

    response = await generate_narrative(
        system_prompt=build_extraction_prompt(field_specs),
        messages=[LLMMessage(role="user", content=document_text)],
    )

    try:
        data = json.loads(response.text.strip())
    except (json.JSONDecodeError, AttributeError):
        return {}

    fields = data.get("fields") if isinstance(data, dict) else None
    if not isinstance(fields, dict):
        return {}

    specs_by_name = {spec.name: spec for spec in field_specs}
    extracted: dict[str, ExtractedField] = {}
    for name, field_data in fields.items():
        spec = specs_by_name.get(name)
        if spec is None or not isinstance(field_data, dict):
            continue
        value = field_data.get("value")
        evidence_span = field_data.get("evidence_span")
        verified = _verify_evidence_span(evidence_span, document_text) and value is not None

        if verified and spec.kind == "date":
            try:
                value = date.fromisoformat(str(value))
            except ValueError:
                verified = False
        elif verified and spec.kind == "enum" and spec.enum_values and value not in spec.enum_values:
            verified = False
        elif verified and spec.kind == "bool" and not isinstance(value, bool):
            if isinstance(value, str) and value.lower() in ("true", "false"):
                value = value.lower() == "true"
            else:
                verified = False

        extracted[name] = ExtractedField(value=value, evidence_span=evidence_span, verified=verified)

    return extracted


def verified_fields_to_computation_inputs(
    rule_name: str, extracted: dict[str, ExtractedField]
) -> tuple[dict[str, Any], list[str]]:
    """Split extracted fields into (usable computation inputs, missing/unverified
    required field names), driven by RULE_FIELD_SPECS so the required/optional
    split always matches what the prompt asked for. Never includes an
    unverified field's value -- a non-empty `missing` list means the caller
    must ask the user to confirm or supply those fields directly rather than
    computing anything.
    """
    inputs: dict[str, Any] = {}
    missing: list[str] = []

    for spec in RULE_FIELD_SPECS.get(rule_name, []):
        extracted_field = extracted.get(spec.name)
        if extracted_field is not None and extracted_field.verified:
            inputs[spec.name] = extracted_field.value
        elif spec.required:
            missing.append(spec.name)

    return inputs, missing
