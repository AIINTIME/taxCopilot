"""Answers "what are the slab rates for AY X?" straight from slab_tables.

A rate-lookup question asks for figures, and the authoritative figures live in
computation/rules/personal/slab_tables.py -- versioned and source-referenced.
So this reads them directly and never touches the LLM. That is the whole point:
the narration prompt forbids the model from stating any rate (the anti-stale
safety control), which also blocks a legitimate "what are the rates" question.
Numbers come from the rate table here, exactly as they do for a computation.

Pure, zero I/O. Returns a plain dict the response layer renders as a table.
"""

import re

from app.services.computation.rules.personal.slab_tables import (
    PersonalRegime,
    RatesNotSeededError,
    get_deduction_limits,
    get_params,
)
from app.services.query.input_extractor import states_income
from app.shared.schemas.tax_year import TaxYearContext

# Asking to be shown the rate table itself -- "what are the slab rates", "tax
# slabs for AY 2025-26", "new regime rates". Distinct from a computation ("what
# is MY tax") because no income is involved: the answer is the table, read from
# slab_tables, not a figure computed for the user.
#
# Kept to phrases that clearly ask for the rate TABLE. Deliberately excludes
# "standard deduction" / "rebate" / "surcharge" on their own: those are as often
# conceptual ("explain the standard deduction" -> retrieval) as lookups, and the
# rate card already lists all three, so a slab-rate lookup shows them anyway.
_RATE_LOOKUP_MARKERS = (
    "slab rate",
    "slab rates",
    "tax slab",
    "tax slabs",
    "slabs for",
    "slab for",
    "rates for",
    "tax rate",
    "tax rates",
    "income tax rate",
    "rate of tax",
    "regime rate",
    "regime rates",
)

# A "how much / what limit" cue. Required for a deduction lookup so that
# "explain 80C" (conceptual -> retrieval) is not mistaken for "what is the 80C
# limit" (figure lookup). Naming a section alone is not enough.
#
# "deduction under" / "rebate under" were here and had to go: they appear in
# ordinary prose that merely REFERS to a section ("home loan interest deduction
# under Section 24(b)"), so they hijacked qualitative questions and answered
# them with a limits table.
_LIMIT_CUE = (
    "limit",
    "maximum",
    "max ",
    "how much",
    "what is the",
    "upto",
    "up to",
    "amount",
    "quantum",
    "deduction available",
)

# Eligibility / interaction questions want reasoning, not a number, even though
# they name sections and may carry a limit cue. "Can I claim both HRA and
# 24(b)?" is answered by retrieval; returning the 24(b) cap answers a question
# nobody asked. These always beat the limit cue.
_ELIGIBILITY_MARKERS = (
    "can i",
    "can a",
    "can an",
    "am i",
    "are we",
    "eligible",
    "both",
    "together",
    "same time",
    "simultaneously",
    "as well as",
    "along with",
    "why",
    "difference between",
    "documents",
)

# Only a backstop, for the case where NO income is stated: "how much tax do I
# pay?" must reach the computation branch so the graph can ask for the figure,
# rather than being shown a rate table it did not ask for. A stated income is
# handled by states_income() and never gets this far.
_COMPUTE_MARKERS = (
    "how much tax",
    "how much do i",
    "calculate",
    "compute",
    "tax liability",
    "tax payable",
    "what tax",
    "what is the tax",
    "what is my tax",
    "what will be my tax",
    "what would be my tax",
    "what will my tax",
    "tax i should pay",
    "tax should i pay",
    "tax i have to pay",
    "tax do i pay",
    "tax to pay",
    "my tax",
    "which regime",
    "old or new",
    "new or old",
    "better regime",
)


def _has(query: str, markers: tuple[str, ...]) -> bool:
    return any(marker in query for marker in markers)


def _band_rows(params) -> list[dict]:
    rows: list[dict] = []
    lower = 0.0
    for band in params.bands:
        if band.upper is None:
            income_range = f"Above {lower:,.0f}"
        else:
            income_range = f"{lower:,.0f} to {band.upper:,.0f}"
        rows.append({"range": income_range, "rate": f"{band.rate:.0%}"})
        lower = band.upper if band.upper is not None else lower
    return rows


def _regime_card(assessment_year: str, regime: PersonalRegime) -> dict | None:
    """Rate card for one regime, or None if that year is not seeded."""
    try:
        params = get_params(assessment_year, regime)
    except RatesNotSeededError:
        return None

    return {
        "regime": regime.value,
        "slab_section": params.slab_section,
        "bands": _band_rows(params),
        "standard_deduction": params.standard_deduction,
        "rebate_87a_income_limit": params.rebate_87a_income_limit,
        "rebate_87a_max": params.rebate_87a_max,
        "cess_rate": params.cess_rate,
        "source_reference": params.source_reference,
    }


# --- Deduction / rebate limit lookups ----------------------------------------
#
# Same principle as the slab card: these figures are authoritative facts in
# slab_tables, so a "what is the 80D limit?" question is answered from the table,
# not the LLM (which is banned from stating figures and would decline). Each
# entry names the section it looks up in slab_tables and how to phrase the
# limit; the query is matched against these to decide which cards to return.
_STANDARD_DEDUCTION = re.compile(r"standard\s+deduction|\b16\s*\(\s*ia\s*\)", re.IGNORECASE)
_REBATE_87A = re.compile(r"\b87\s*-?\s*a\b|rebate", re.IGNORECASE)
_DEDUCTION_TRIGGERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("section_80c", re.compile(r"\b80\s*-?\s*c\b", re.IGNORECASE)),
    ("section_80d", re.compile(r"\b80\s*-?\s*d\b", re.IGNORECASE)),
    ("section_80tta", re.compile(r"\b80\s*-?\s*tta\b", re.IGNORECASE)),
    ("home_loan_interest_24b", re.compile(r"\b24\s*\(\s*b\s*\)|home\s+loan\s+interest", re.IGNORECASE)),
)


def _deduction_entry(field: str, limits) -> dict | None:
    if field == "section_80c":
        return {"item": "Sec 80C", "limit": f"{limits.section_80c:,.0f}",
                "note": "Old regime only; not available under the new regime."}
    if field == "section_80d":
        return {"item": "Sec 80D", "limit": f"{limits.section_80d_self:,.0f} (self/family)",
                "note": f"Up to {limits.section_80d_parents_senior:,.0f} additional for senior-citizen parents."}
    if field == "section_80tta":
        return {"item": "Sec 80TTA", "limit": f"{limits.section_80tta:,.0f}",
                "note": "On savings-account interest."}
    if field == "home_loan_interest_24b":
        return {"item": "Sec 24(b)", "limit": f"{limits.home_loan_interest_24b:,.0f}",
                "note": "Interest on a self-occupied housing loan."}
    return None


def detect_deduction_query(query: str) -> bool:
    """True when the query names a specific deduction/rebate whose limit lives
    in slab_tables -- 80C/80D/80TTA/24(b)/standard deduction/87A.
    """
    if _STANDARD_DEDUCTION.search(query) or _REBATE_87A.search(query):
        return True
    return any(pattern.search(query) for _, pattern in _DEDUCTION_TRIGGERS)


def detect_rate_query(query: str) -> bool:
    """True when the query asks to be shown the rate table itself.

    A stated income (or an explicit compute phrasing) always wins: "what are the
    slab rates?" is a lookup, but "my salary is 21L, what rate applies?" states
    an input and must compute.
    """
    lowered = query.lower()
    if not _has(lowered, _RATE_LOOKUP_MARKERS):
        return False
    return not states_income(query) and not _has(lowered, _COMPUTE_MARKERS)


def detect_deduction_lookup(query: str) -> bool:
    """True when the query asks for a deduction/rebate LIMIT: it names a section
    AND asks how much, with no income stated.

    "What is the 80D limit?" -> the figure from slab_tables. "Explain 80D" ->
    retrieval, for lacking the limit cue. "Can I claim 80C and 80D together?" ->
    retrieval, because eligibility beats the cue: answering it with a limits
    table answers a question nobody asked.
    """
    lowered = query.lower()
    return (
        not states_income(query)
        and not _has(lowered, _COMPUTE_MARKERS)
        and not _has(lowered, _ELIGIBILITY_MARKERS)
        and _has(lowered, _LIMIT_CUE)
        and detect_deduction_query(query)
    )


def build_deduction_card(as_of: TaxYearContext, query: str) -> dict:
    """Limit(s) for the deduction/rebate the query names, from slab_tables."""
    ay = as_of.assessment_year.ay
    entries: list[dict] = []

    try:
        limits = get_deduction_limits(ay)
    except RatesNotSeededError:
        limits = None

    if limits is not None:
        for field, pattern in _DEDUCTION_TRIGGERS:
            if pattern.search(query):
                entry = _deduction_entry(field, limits)
                if entry:
                    entry["source_reference"] = limits.source_reference
                    entries.append(entry)

    if _STANDARD_DEDUCTION.search(query):
        for regime in (PersonalRegime.NEW, PersonalRegime.OLD):
            try:
                p = get_params(ay, regime)
            except RatesNotSeededError:
                continue
            entries.append({
                "item": f"Standard deduction ({regime.value} regime)",
                "limit": f"{p.standard_deduction:,.0f}",
                "note": "Salaried individuals, Sec 16(ia).",
                "source_reference": p.source_reference,
            })

    if _REBATE_87A.search(query):
        for regime in (PersonalRegime.NEW, PersonalRegime.OLD):
            try:
                p = get_params(ay, regime)
            except RatesNotSeededError:
                continue
            entries.append({
                "item": f"Sec 87A rebate ({regime.value} regime)",
                "limit": f"up to {p.rebate_87a_max:,.0f}",
                "note": f"When total income does not exceed {p.rebate_87a_income_limit:,.0f}.",
                "source_reference": p.source_reference,
            })

    return {"assessment_year": ay, "available": bool(entries), "entries": entries}


def build_rate_card(
    as_of: TaxYearContext, regime: PersonalRegime | None = None
) -> dict:
    """Rate card for the resolved assessment year.

    `regime` narrows to one scheme; None returns both. When the year is not
    seeded, `regimes` is empty and `available` is False -- the caller must say
    "rates for AY X are not available" rather than guess an adjacent year, per
    the RatesNotSeededError contract.
    """
    ay = as_of.assessment_year.ay
    wanted = [regime] if regime is not None else [PersonalRegime.NEW, PersonalRegime.OLD]

    cards = [card for r in wanted if (card := _regime_card(ay, r)) is not None]

    return {
        "assessment_year": ay,
        "available": bool(cards),
        "regimes": cards,
    }
