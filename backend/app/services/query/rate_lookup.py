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
from app.shared.schemas.tax_year import TaxYearContext


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
