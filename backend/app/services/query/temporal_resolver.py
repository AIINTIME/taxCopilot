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

# "AY 2025-26" / "AY 2025-2026" / "assessment year 2025-26"
_AY_PATTERN = re.compile(
    r"\b(?:AY|assessment year)\s*(\d{4})\s*-\s*(\d{2,4})\b", re.IGNORECASE
)
# "FY 2024-25" / "financial year 2024-25"
_FY_PATTERN = re.compile(
    r"\b(?:FY|financial year)\s*(\d{4})\s*-\s*(\d{2,4})\b", re.IGNORECASE
)
# ISO or common date formats, e.g. 2025-07-15, 15/07/2025, 15-07-2025
_DATE_PATTERN = re.compile(
    r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b|\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"
)


def _assessment_year_for(as_of_date: date) -> AssessmentYear:
    """India's FY runs 1 Apr - 31 Mar; AY is the year immediately following FY."""
    if as_of_date.month >= 4:
        fy_start_year = as_of_date.year
    else:
        fy_start_year = as_of_date.year - 1

    financial_year = f"{fy_start_year}-{str(fy_start_year + 1)[-2:]}"
    ay = f"{fy_start_year + 1}-{str(fy_start_year + 2)[-2:]}"
    return AssessmentYear(ay=ay, financial_year=financial_year)


def _parse_date_from_query(query: str) -> date | None:
    ay_match = _AY_PATTERN.search(query)
    if ay_match:
        fy_start_year = int(ay_match.group(1)) - 1
        return date(fy_start_year, 4, 1)

    fy_match = _FY_PATTERN.search(query)
    if fy_match:
        return date(int(fy_match.group(1)), 4, 1)

    date_match = _DATE_PATTERN.search(query)
    if date_match:
        if date_match.group(1):
            year, month, day = date_match.group(1), date_match.group(2), date_match.group(3)
        else:
            day, month, year = date_match.group(4), date_match.group(5), date_match.group(6)
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None

    return None


def resolve_as_of(query: str, explicit_date: date | None = None) -> TaxYearContext:
    as_of_date = explicit_date or _parse_date_from_query(query) or date.today()

    regime = (
        TaxActRegime.ACT_2025
        if as_of_date >= ACT_2025_EFFECTIVE_DATE
        else TaxActRegime.ACT_1961
    )
    capital_gains_period = (
        CapitalGainsPeriod.POST_RATE_CHANGE
        if as_of_date >= CG_RATE_CHANGE_DATE
        else CapitalGainsPeriod.PRE_RATE_CHANGE
    )

    return TaxYearContext(
        as_of_date=as_of_date,
        assessment_year=_assessment_year_for(as_of_date),
        regime=regime,
        capital_gains_period=capital_gains_period,
    )
