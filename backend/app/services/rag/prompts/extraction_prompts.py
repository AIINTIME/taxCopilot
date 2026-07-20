"""System prompt builder for services.rag.extraction.document_extraction --
query-time extraction of structured computation figures from a user's
uploaded document (e.g. a sale deed, P&L statement, or broker contract note).

Same evidence-span discipline as
services/ingestion/kg_graph_extraction/rule_proposal.py's statutory-rule
extraction: the LLM may only report a field it can point to verbatim in the
source text, never infer/estimate/round one. Every field is independently
re-verified against the source text after this call
(services/rag/extraction/document_extraction.py) -- this prompt is a
best-effort request, not the trust boundary itself.

One generic prompt, parameterized by a per-rule field spec list, rather than
a hand-written prompt per computation rule -- the field list is the single
source of truth (document_extraction.py's RULE_FIELD_SPECS), so a new rule
or a changed field name here never has a second copy to fall out of sync.
"""

from dataclasses import dataclass

FieldKind = str  # "number" | "date" | "enum" | "bool"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: FieldKind
    required: bool
    enum_values: tuple[str, ...] | None = None
    description: str = ""


def _field_schema_line(spec: FieldSpec) -> str:
    if spec.kind == "enum" and spec.enum_values:
        value_type = " | ".join(f'"{v}"' for v in spec.enum_values)
    elif spec.kind == "date":
        value_type = '"YYYY-MM-DD"'
    elif spec.kind == "bool":
        value_type = "true | false"
    else:
        value_type = "number"

    suffix = f" -- {spec.description}" if spec.description else ""
    return f'    "{spec.name}": {{"value": {value_type}, "evidence_span": string}} | null{suffix}'


def build_extraction_prompt(field_specs: list[FieldSpec]) -> str:
    schema_lines = "\n".join(_field_schema_line(spec) for spec in field_specs)

    return f"""You are a tax document field extractor.

Given the text of a user's document (e.g. a sale deed, filed return, P&L
statement, or broker contract note), extract the fields below -- if and only
if they are explicitly stated in the text. Respond with ONLY a valid JSON
object. No markdown fences, no explanation, no preamble.

Schema:
{{
  "fields": {{
{schema_lines}
  }}
}}

Rules you must follow:
- Set a field to null if it is not explicitly stated in the text -- do NOT
  infer, estimate, round, or guess a value.
- Dates must be normalized to YYYY-MM-DD only when the source text states an
  unambiguous calendar date; if the date is ambiguous or only a year/month is
  given, set the field to null rather than guessing a day.
- evidence_span MUST be copied verbatim as a substring from the input text
  (the exact phrase that states the value) -- if you cannot find a verbatim
  substring supporting a field, set that field to null.
- Do NOT combine or calculate values (e.g. do not sum multiple payments into
  a total) -- extract only values stated directly as a single figure.
"""
