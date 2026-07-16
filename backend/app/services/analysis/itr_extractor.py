"""Uploaded ITR / Form 16 -> the structured facts reconciler needs.

Reuses ingestion/parsing/pdf_parser.parse_pdf for text extraction. Chunking is
deliberately NOT reused: chunk_document splits on fixed character counts for
embedding, which would cut a figure away from the label that identifies it.

Deterministic label-and-amount matching, never an LLM. Same reasoning as
query/input_extractor and computation/validators: a figure invented or
misattributed here flows straight into a recomputation that is then presented
as exact, and the resulting error would carry the full authority of a
computation trace. An unreadable field must be reported missing so a human can
supply it -- see `missing`.

Every extracted figure keeps the line it came from in `provenance`, the same
discipline kg_graph_extraction applies with evidence_span: a number nobody can
trace back to the document is a number nobody can check.
"""

import re
from dataclasses import dataclass, field

from app.services.computation.rules.personal.deduction_sections import SECTION_PATTERNS
from app.services.computation.rules.personal.deductions import DeductionInputs
from app.services.computation.rules.personal.regime_comparison_personal import IncomeType
from app.services.computation.rules.personal.slab_tables import PersonalRegime
from app.services.analysis.reconciler import FiledReturn
from app.services.ingestion.parsing.pdf_parser import parse_pdf

# Indian-format amount, optionally prefixed by a currency marker. Deliberately
# stricter than input_extractor's parser: a filed return states figures in
# digits, so lakh/crore words are not expected and a bare "5" on a form is far
# more likely to be a row number than five rupees.
_AMOUNT = re.compile(r"(?:rs\.?|inr|₹)?\s*([0-9][0-9,]{2,})(?:\.\d{1,2})?")

_GROSS_INCOME_LABELS = (
    "gross total income",
    "gross salary",
    "total income",
    "income from salary",
)
_TAX_LABELS = (
    "total tax payable",
    "tax payable",
    "net tax payable",
    "total tax liability",
)
# Section recognition comes from computation/rules/personal/deduction_sections --
# the same vocabulary query/input_extractor uses on prose, so a section the chat
# understands is a section a form can be read for. See that module on why the
# patterns are word-bounded rather than substrings.

_NEW_REGIME_MARKERS = ("115bac", "new tax regime", "new regime", "default regime")
_OLD_REGIME_MARKERS = ("old tax regime", "old regime", "opted out")

_SALARY_MARKERS = ("form 16", "salary", "employer", "tds on salary")
_BUSINESS_MARKERS = ("business", "profession", "presumptive", "44ad", "44ada")


@dataclass(frozen=True)
class ExtractedReturn:
    filed: FiledReturn | None
    missing: tuple[str, ...]
    provenance: dict[str, str] = field(default_factory=dict)

    @property
    def is_usable(self) -> bool:
        return self.filed is not None


def _amount_on_line(line: str) -> float | None:
    """Rightmost amount on a line -- forms put the label left, the figure right."""
    matches = _AMOUNT.findall(line)
    if not matches:
        return None
    try:
        return float(matches[-1].replace(",", ""))
    except ValueError:
        return None


def _find_labelled(lines: list[str], labels: tuple[str, ...]) -> tuple[float, str] | None:
    for line in lines:
        lowered = line.lower()
        if any(label in lowered for label in labels):
            amount = _amount_on_line(line)
            if amount is not None and amount > 0:
                return amount, line.strip()
    return None


def _find_by_pattern(lines: list[str], pattern: re.Pattern[str]) -> tuple[float, str] | None:
    for line in lines:
        if pattern.search(line):
            amount = _amount_on_line(line)
            if amount is not None and amount > 0:
                return amount, line.strip()
    return None


def _line_containing(lines: list[str], markers: tuple[str, ...]) -> str | None:
    """First line mentioning any marker -- the source line for a detected fact,
    so provenance stays "the line it came from" rather than the parsed value.
    """
    for line in lines:
        lowered = line.lower()
        if any(m in lowered for m in markers):
            return line.strip()
    return None


def _detect_regime(text: str) -> PersonalRegime | None:
    lowered = text.lower()
    new_hit = any(m in lowered for m in _NEW_REGIME_MARKERS)
    old_hit = any(m in lowered for m in _OLD_REGIME_MARKERS)

    # Both mentioned is common -- forms print the election as a choice. Neither
    # wins; ask rather than coin-flip the regime the whole reconciliation is
    # measured against.
    if new_hit and not old_hit:
        return PersonalRegime.NEW
    if old_hit and not new_hit:
        return PersonalRegime.OLD
    return None


def _detect_income_type(text: str) -> IncomeType | None:
    lowered = text.lower()
    if any(m in lowered for m in _BUSINESS_MARKERS):
        return IncomeType.BUSINESS
    if any(m in lowered for m in _SALARY_MARKERS):
        return IncomeType.SALARY
    return None


def extract_from_text(text: str) -> ExtractedReturn:
    lines = [line for line in text.splitlines() if line.strip()]
    provenance: dict[str, str] = {}
    missing: list[str] = []

    gross = _find_labelled(lines, _GROSS_INCOME_LABELS)
    if gross:
        provenance["gross_income"] = gross[1]
    else:
        missing.append("gross_income")

    regime = _detect_regime(text)
    if regime:
        provenance["regime_filed"] = (
            _line_containing(lines, _NEW_REGIME_MARKERS + _OLD_REGIME_MARKERS)
            or regime.value
        )
    else:
        missing.append("regime_filed")

    income_type = _detect_income_type(text)
    if income_type:
        provenance["income_type"] = (
            _line_containing(lines, _SALARY_MARKERS + _BUSINESS_MARKERS)
            or income_type.value
        )
    else:
        missing.append("income_type")

    claimed: dict[str, float] = {}
    for field_name, pattern in SECTION_PATTERNS.items():
        found = _find_by_pattern(lines, pattern)
        if found:
            claimed[field_name] = found[0]
            provenance[field_name] = found[1]

    declared_tax = _find_labelled(lines, _TAX_LABELS)
    if declared_tax:
        provenance["declared_tax"] = declared_tax[1]

    # gross_income, regime and income_type are all load-bearing: without any one
    # of them the recomputation is not comparable to the return. Missing
    # deductions are fine -- absent means not claimed.
    if missing:
        return ExtractedReturn(filed=None, missing=tuple(missing), provenance=provenance)

    return ExtractedReturn(
        filed=FiledReturn(
            gross_income=gross[0],
            income_type=income_type,
            regime_filed=regime,
            deductions=DeductionInputs(**claimed),
            declared_tax=declared_tax[0] if declared_tax else None,
            provenance=provenance,
        ),
        missing=(),
        provenance=provenance,
    )


def extract_from_pdf(content: bytes) -> ExtractedReturn:
    return extract_from_text(parse_pdf(content))
