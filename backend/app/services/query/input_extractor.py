"""Derives computation inputs from a natural-language query. Pure, zero I/O.

Deterministic and rule-based, NEVER an LLM. Intent classification tells the
graph WHICH rule to run; this tells it WHAT to run the rule on. Both are
control-flow decisions, and per the architecture the LLM makes neither -- and
per validators.py, "every number must be sourced, never an LLM guess". A
hallucinated input silently corrupts an otherwise exact computation, which is
the worst failure this system can produce: wrong, and confidently traced.

Where a required fact is absent, this returns it in `missing` rather than
guessing a default. Computing "exactly" on an invented input is worse than
asking one question.
"""

import re
from dataclasses import dataclass, field

from app.services.computation.rules.personal.regime_comparison_personal import IncomeType

# Indian numbering: 1 lakh = 1e5, 1 crore = 1e7. A bare "5" in "5 lakhs" is a
# multiplier, not the amount -- a naive number parser reads it as 5 rupees.
_MULTIPLIERS: dict[str, float] = {
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "l": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "cr": 10_000_000,
    "k": 1_000,
}

_AMOUNT_PATTERN = re.compile(
    r"(?:rs\.?|inr|₹)?\s*"
    r"(\d[\d,]*(?:\.\d+)?)\s*"
    r"(lakhs?|lacs?|crores?|cr|l|k)?\b",
    re.IGNORECASE,
)

_INCOME_TYPE_MARKERS: tuple[tuple[IncomeType, tuple[str, ...]], ...] = (
    (IncomeType.SALARY, ("salary", "salaried", "ctc", "form 16", "form-16", "employer")),
    (
        IncomeType.BUSINESS,
        ("business", "profession", "freelance", "consultancy", "self-employed", "proprietor"),
    ),
)

# Words that indicate the number following is not the income figure.
_YEAR_CONTEXT = re.compile(r"\b(?:a\.?y\.?|f\.?y\.?|assessment|financial)\s*year\b", re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedInputs:
    values: dict[str, float] = field(default_factory=dict)
    income_type: IncomeType | None = None
    assumptions: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    provenance: dict[str, str] = field(default_factory=dict)

    @property
    def needs_clarification(self) -> bool:
        return bool(self.missing)

    def to_rule_inputs(self) -> dict[str, object]:
        """Shape expected by computation.engine.compute()'s `inputs` mapping.

        Only meaningful once `needs_clarification` is False -- the graph must
        route to clarification before calling this.
        """
        return {**self.values, "income_type": self.income_type}


CLARIFICATION_PROMPTS: dict[str, str] = {
    "gross_income": "What is your total annual income?",
    "income_type": "Is that salary income, or business/professional income? "
    "Only salary attracts the standard deduction, so it changes the figure.",
}


def clarification_questions(extracted: ExtractedInputs) -> list[str]:
    return [CLARIFICATION_PROMPTS[m] for m in extracted.missing if m in CLARIFICATION_PROMPTS]


def parse_amount(text: str) -> float | None:
    """Parse a single Indian-notation amount. Returns None if unparseable.

    Exposed for direct unit testing -- the numeral handling is the part most
    likely to break silently.
    """
    match = _AMOUNT_PATTERN.search(text.strip())
    if not match:
        return None
    return _amount_from_match(match)


def _amount_from_match(match: re.Match[str]) -> float | None:
    digits = match.group(1).replace(",", "")
    try:
        value = float(digits)
    except ValueError:
        return None

    unit = (match.group(2) or "").lower()
    if unit:
        return value * _MULTIPLIERS[unit]

    # A bare number with no unit is taken at face value. "5,00,000" is already
    # 500000 once commas are stripped; Indian grouping needs no special case.
    return value


def _detect_income_type(query: str) -> IncomeType | None:
    lowered = query.lower()
    for income_type, markers in _INCOME_TYPE_MARKERS:
        if any(marker in lowered for marker in markers):
            return income_type
    return None


def _find_income_amount(query: str) -> tuple[float, str] | None:
    """Largest plausible amount in the query, with the span it came from.

    Largest wins because a query mentioning both an income and a deduction
    ("21 lakhs salary, 1.5 lakh 80C") states the income as the bigger figure.
    Spans overlapping a year mention are skipped so "AY 2026-27" is not read
    as an amount.
    """
    best: tuple[float, str] | None = None

    for match in _AMOUNT_PATTERN.finditer(query):
        window = query[max(0, match.start() - 20) : match.end() + 10]
        if _YEAR_CONTEXT.search(window):
            continue

        amount = _amount_from_match(match)
        if amount is None or amount <= 0:
            continue

        if best is None or amount > best[0]:
            best = (amount, match.group(0).strip())

    return best


def extract_inputs(query: str) -> ExtractedInputs:
    """Extract personal-tax computation inputs from a query.

    Scope: the gross income figure and the income type. Per-section deduction
    extraction is deliberately not attempted yet -- an under-read deduction
    biases the regime recommendation toward the new regime, so deductions are
    better collected explicitly than guessed at. regime_comparison_personal's
    `breakeven_deductions` covers the gap by reporting the threshold at which
    the answer would flip.
    """
    values: dict[str, float] = {}
    provenance: dict[str, str] = {}
    assumptions: list[str] = []
    missing: list[str] = []

    found = _find_income_amount(query)
    if found is None:
        missing.append("gross_income")
    else:
        amount, span = found
        values["gross_income"] = amount
        provenance["gross_income"] = span

    income_type = _detect_income_type(query)
    if income_type is None:
        # Materially changes the answer: only salary attracts the standard
        # deduction, so assuming it would silently understate tax for a
        # business filer. Ask instead.
        missing.append("income_type")
    else:
        provenance["income_type"] = income_type.value

    if income_type is not None and "deduction" not in query.lower():
        assumptions.append(
            "No deductions (80C/80D/HRA) were stated, so none were claimed"
        )

    return ExtractedInputs(
        values=values,
        income_type=income_type,
        assumptions=tuple(assumptions),
        missing=tuple(missing),
        provenance=provenance,
    )
