"""Derives computation inputs from a natural-language query. Pure, zero I/O.

Deterministic and rule-based -- extract_inputs() itself never calls an LLM.
Not currently wired into the live query flow (services.query.
llm_query_understanding.classify_and_extract is the sole extractor there, with
no deterministic fallback); kept as a standalone, still-tested utility.
`parse_amount` and `detect_income_type` ARE actively used, though -- by
llm_query_understanding.py: the LLM may point at a span of the query, but the
number/type that actually reaches the computation engine always comes from
re-parsing that span with the two functions below, never from the LLM's own
stated value. Per validators.py, "every number must be sourced, never an LLM
guess" -- a hallucinated input silently corrupts an otherwise exact
computation, which is the worst failure this system can produce: wrong, and
confidently traced.

AMOUNTS ARE BOUND TO THE LABEL THAT GIVES THEM MEANING, never ranked. An
earlier version took the largest number in the query as the income, which
inverts the moment a deduction exceeds it -- "salary is 5 lakhs and I have HRA
of 6 lakhs" read the HRA as the salary. Each figure here is claimed by the
nearest income or section label, and a span claimed once cannot be claimed
again.

Where a required fact is absent, this returns it in `missing` rather than
guessing a default. Computing "exactly" on an invented input is worse than
asking one question.
"""

import re
from dataclasses import dataclass, field

from app.services.computation.rules.personal.deduction_sections import (
    SECTION_LABELS,
    SECTION_PATTERNS,
)
from app.services.computation.rules.personal.regime_comparison_personal import IncomeType

# Indian numbering: 1 lakh = 1e5, 1 crore = 1e7. A bare "5" in "5 lakhs" is a
# multiplier, not the amount -- a naive number parser reads it as 5 rupees.
#
# "lpa" (lakhs per annum) is the single most common way an Indian salary is
# stated and MUST be here: without it "18 lpa" parses as eighteen rupees and
# returns a tax of zero, entirely plausibly.
_MULTIPLIERS: dict[str, float] = {
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "lpa": 100_000,
    "l.p.a": 100_000,
    "lpa.": 100_000,
    "l": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "cr": 10_000_000,
    "k": 1_000,
}

# Longest units first so "lpa" is not consumed as a bare "l" with "pa" left over.
_UNIT_ALTERNATION = "|".join(
    re.escape(unit) for unit in sorted(_MULTIPLIERS, key=len, reverse=True)
)

_AMOUNT_PATTERN = re.compile(
    r"(?:rs\.?|inr|₹)?\s*"
    r"(\d[\d,]*(?:\.\d+)?)\s*"
    rf"({_UNIT_ALTERNATION})?\b",
    re.IGNORECASE,
)

_INCOME_LABEL = re.compile(
    r"\b(?:salary|salaries|income|ctc|earn(?:ing|s)?|package|remuneration|pay)\b",
    re.IGNORECASE,
)

_INCOME_TYPE_MARKERS: tuple[tuple[IncomeType, tuple[str, ...]], ...] = (
    (IncomeType.SALARY, ("salary", "salaried", "ctc", "form 16", "form-16", "employer", "lpa")),
    (
        IncomeType.BUSINESS,
        ("business", "profession", "freelance", "consultancy", "self-employed", "proprietor"),
    ),
)

# Disposals imply capital gains, whose rule is still a stub. Detected only so
# the answer can say it ignored them -- silently dropping a share sale from a
# tax computation would be a wrong answer wearing a full audit trail.
_CAPITAL_GAINS_MARKERS = (
    "mutual fund",
    "shares",
    "equity",
    "capital gain",
    "sold",
    "redeemed",
    "property sale",
)

# Words that indicate the number following is not an amount.
_YEAR_CONTEXT = re.compile(
    r"\b(?:a\.?y\.?|f\.?y\.?|assessment|financial)\s*year\b|\b(?:ay|fy)\s*\d{4}", re.IGNORECASE
)

# How far from a label an amount may sit and still be claimed by it. Wide enough
# for "HRA of about 4 lakhs", narrow enough that the next clause's figure is not
# stolen.
_BIND_WINDOW = 40


@dataclass(frozen=True)
class _Amount:
    value: float
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class _Label:
    """A word that can claim an amount: "salary", or a section like "80C"."""

    kind: str  # "gross_income", or a DeductionInputs field name
    start: int
    end: int


@dataclass(frozen=True)
class ExtractedInputs:
    values: dict[str, float] = field(default_factory=dict)
    income_type: IncomeType | None = None
    deductions: dict[str, float] = field(default_factory=dict)
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
        return {
            **self.values,
            "income_type": self.income_type,
            "deductions": dict(self.deductions),
        }


CLARIFICATION_PROMPTS: dict[str, str] = {
    "gross_income": "What is your total annual income?",
    "income_type": "Is that salary income, or business/professional income? "
    "Only salary attracts the standard deduction, so it changes the figure.",
}


def clarification_questions(missing: tuple[str, ...] | list[str]) -> list[str]:
    return [CLARIFICATION_PROMPTS[m] for m in missing if m in CLARIFICATION_PROMPTS]


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


def parse_amount(text: str) -> float | None:
    """Parse a single Indian-notation amount. Returns None if unparseable.

    Exposed for direct unit testing -- the numeral handling is the part most
    likely to break silently.
    """
    match = _AMOUNT_PATTERN.search(text.strip())
    if not match:
        return None
    return _amount_from_match(match)


def _find_amounts(query: str) -> list[_Amount]:
    found: list[_Amount] = []
    for match in _AMOUNT_PATTERN.finditer(query):
        window = query[max(0, match.start() - 20) : match.end() + 10]
        if _YEAR_CONTEXT.search(window):
            continue
        value = _amount_from_match(match)
        if value is None or value <= 0:
            continue
        found.append(
            _Amount(value=value, start=match.start(), end=match.end(), text=match.group(0).strip())
        )
    return found


def _distance(label: _Label, amount: _Amount) -> int:
    """Characters between a label and an amount, or -1 if they do not pair.

    "HRA of 4 lakhs" puts the figure after the label; "1.5 lakhs in 80C" puts it
    before. Both are natural, so both count -- but a preceding amount is charged
    +1, so a following one wins a tie, that being the commoner phrasing.
    """
    if amount.start >= label.end:
        return amount.start - label.end
    return label.start - amount.end + 1


def _bind_labels_to_amounts(
    labels: list[_Label], amounts: list[_Amount]
) -> dict[str, _Amount]:
    """Assign each amount to its nearest label, globally.

    Greedy over the closest pair first, rather than resolving one kind of label
    before another. Order-by-kind looks reasonable and is wrong: in "my salary
    is 21 lakhs, I have HRA and sold one mutual fund", binding deductions first
    lets HRA -- 11 characters away -- claim the salary figure, leaving the income
    empty. Nearest-first gives "salary" the figure it is sitting next to, and
    HRA correctly ends up with nothing.
    """
    pairs: list[tuple[int, int, _Label, _Amount]] = []
    for label in labels:
        for amount in amounts:
            distance = _distance(label, amount)
            if 0 <= distance <= _BIND_WINDOW:
                # amount.start is a stable tiebreak, so binding is deterministic.
                pairs.append((distance, amount.start, label, amount))

    pairs.sort(key=lambda pair: (pair[0], pair[1]))

    bound: dict[str, _Amount] = {}
    used: set[int] = set()
    for _, _, label, amount in pairs:
        if label.kind in bound or amount.start in used:
            continue
        bound[label.kind] = amount
        used.add(amount.start)

    return bound


def states_income(query: str) -> bool:
    """True when the query states an income figure -- "my salary is 19 lakhs".

    The reliable signal that an amount is an INPUT to compute on rather than the
    subject of a question. "What is the 80C limit of 1.5 lakh" also names a
    figure, but that figure belongs to the section, so this returns False.

    Exported for intent_classifier, which cannot route on question phrasing
    alone: "what is my payable tax" and "what is HRA" open identically.
    """
    label = _INCOME_LABEL.search(query)
    if not label:
        return False

    income_label = _Label("gross_income", label.start(), label.end())
    return any(
        0 <= _distance(income_label, amount) <= _BIND_WINDOW
        for amount in _find_amounts(query)
    )


def detect_income_type(query: str) -> IncomeType | None:
    """Re-derive an income type from a span of text via the marker list below.

    Public (not `_`-prefixed): also used by llm_query_understanding.py to
    verify an LLM-proposed income_type against the evidence span it cited,
    rather than trusting the LLM's own classification of the span.
    """
    lowered = query.lower()
    for income_type, markers in _INCOME_TYPE_MARKERS:
        if any(marker in lowered for marker in markers):
            return income_type
    return None


def extract_inputs(query: str) -> ExtractedInputs:
    """Extract personal-tax computation inputs from a query."""
    amounts = _find_amounts(query)

    labels: list[_Label] = []
    for match in _INCOME_LABEL.finditer(query):
        labels.append(_Label("gross_income", match.start(), match.end()))
    mentioned_sections: set[str] = set()
    for field_name, pattern in SECTION_PATTERNS.items():
        for match in pattern.finditer(query):
            labels.append(_Label(field_name, match.start(), match.end()))
            mentioned_sections.add(field_name)

    bound = _bind_labels_to_amounts(labels, amounts)

    values: dict[str, float] = {}
    deductions: dict[str, float] = {}
    provenance: dict[str, str] = {}
    assumptions: list[str] = []
    missing: list[str] = []

    for field_name in mentioned_sections:
        amount = bound.get(field_name)
        if amount is None:
            # Named without a figure -- "I have HRA". Nothing to compute with,
            # but the user did raise it, so say so rather than ignoring it.
            assumptions.append(
                f"{SECTION_LABELS[field_name]} was mentioned without an amount, "
                f"so it could not be included"
            )
            continue
        deductions[field_name] = amount.value
        provenance[field_name] = amount.text

    income = bound.get("gross_income")
    if income is None:
        # No income label, or none near one: fall back to the largest figure no
        # section claimed ("21 lakhs" on its own).
        spoken_for = {a.start for a in bound.values()}
        unclaimed = [a for a in amounts if a.start not in spoken_for]
        income = max(unclaimed, key=lambda a: a.value) if unclaimed else None

    if income is None:
        missing.append("gross_income")
    else:
        values["gross_income"] = income.value
        provenance["gross_income"] = income.text

    income_type = detect_income_type(query)
    if income_type is None:
        # Materially changes the answer: only salary attracts the standard
        # deduction, so assuming it would silently understate tax for a
        # business filer. Ask instead.
        missing.append("income_type")
    else:
        provenance["income_type"] = income_type.value

    if not deductions and not mentioned_sections and income_type is not None:
        # Says what is true -- that nothing was READ -- rather than asserting
        # what the user did or did not say. The previous wording ("no deductions
        # were stated") fired whenever the literal word "deduction" was absent,
        # so it told people who had just mentioned HRA that they had not.
        #
        # Suppressed when a section WAS named but carried no figure: the
        # per-section note above already says so, and following it with "no
        # deductions were read" contradicts it.
        assumptions.append(
            "No deductions (80C/80D/HRA) were read from your question, so none were applied"
        )

    lowered = query.lower()
    if any(marker in lowered for marker in _CAPITAL_GAINS_MARKERS):
        assumptions.append(
            "A sale or capital asset was mentioned; capital gains are not yet "
            "computed and are excluded from these figures"
        )

    return ExtractedInputs(
        values=values,
        income_type=income_type,
        deductions=deductions,
        assumptions=tuple(assumptions),
        missing=tuple(missing),
        provenance=provenance,
    )
