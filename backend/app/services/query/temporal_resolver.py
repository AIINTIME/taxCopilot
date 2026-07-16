"""Resolves the as-of date / Assessment Year / Tax Year / regime for a query.

This must run FIRST, before computation or retrieval, per the architecture's
temporal-resolution-first rule. It must branch on the two hard pivot dates
defined in app.shared.schemas.tax_year:

- CG_RATE_CHANGE_DATE (23 Jul 2024): which side of the capital-gains
  rate/indexation change a query's as-of date falls on.
- ACT_2025_EFFECTIVE_DATE (1 Apr 2026): whether the 1961 Act or the 2025 Act
  applies as of that date.
"""

import re
from datetime import date

from app.shared.schemas.tax_year import (
    ACT_2025_EFFECTIVE_DATE,
    CG_RATE_CHANGE_DATE,
    AssessmentYear,
    CapitalGainsPeriod,
    TaxActRegime,
    TaxYearContext,
)

# Deterministic, keyword/pattern based -- never an LLM call, per the
# architecture's "temporal resolution must run first, control flow is never
# an LLM decision" rule.
_AY_PATTERN = re.compile(r"\bAY\s*(\d{4})-(\d{2})\b|\bassessment\s+year\s*(\d{4})-(\d{2})\b", re.IGNORECASE)
_FY_PATTERN = re.compile(r"\bFY\s*(\d{4})-(\d{2})\b|\bfinancial\s+year\s*(\d{4})-(\d{2})\b", re.IGNORECASE)


def _fy_start_year_from_query(query: str) -> int | None:
    ay_match = _AY_PATTERN.search(query)
    if ay_match:
        ay_start = int(ay_match.group(1) or ay_match.group(3))
        return ay_start - 1  # AY 2025-26 -> FY 2024-25

    fy_match = _FY_PATTERN.search(query)
    if fy_match:
        return int(fy_match.group(1) or fy_match.group(3))

    return None


def _financial_year_bounds(as_of_date: date) -> int:
    """Return the FY start year (e.g. 2024 for FY "2024-25") for `as_of_date`."""
    return as_of_date.year if as_of_date.month >= 4 else as_of_date.year - 1


def resolve_as_of(query: str, explicit_date: date | None = None) -> TaxYearContext:
    if explicit_date is not None:
        as_of_date = explicit_date
    else:
        fy_start_year = _fy_start_year_from_query(query)
        # Anchor to the last day of the mentioned FY (31 Mar of the following
        # calendar year) so regime/rate-change branching reflects that year.
        as_of_date = date(fy_start_year + 1, 3, 31) if fy_start_year is not None else date.today()

    fy_start_year = _financial_year_bounds(as_of_date)
    financial_year = f"{fy_start_year}-{str(fy_start_year + 1)[-2:]}"
    ay_start_year = fy_start_year + 1
    ay = f"{ay_start_year}-{str(ay_start_year + 1)[-2:]}"

    regime = TaxActRegime.ACT_2025 if as_of_date >= ACT_2025_EFFECTIVE_DATE else TaxActRegime.ACT_1961
    capital_gains_period = (
        CapitalGainsPeriod.POST_RATE_CHANGE
        if as_of_date >= CG_RATE_CHANGE_DATE
        else CapitalGainsPeriod.PRE_RATE_CHANGE
    )

    return TaxYearContext(
        as_of_date=as_of_date,
        assessment_year=AssessmentYear(ay=ay, financial_year=financial_year),
        regime=regime,
        capital_gains_period=capital_gains_period,
    )
