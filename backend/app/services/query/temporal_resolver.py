"""Resolves the as-of date / Assessment Year / Tax Year / regime for a query.

This must run FIRST, before computation or retrieval, per the architecture's
temporal-resolution-first rule. It branches on the two hard pivot dates
defined in app.shared.schemas.tax_year:

- CG_RATE_CHANGE_DATE (23 Jul 2024): which side of the capital-gains
  rate/indexation change a transfer falls on.
- ACT_2025_EFFECTIVE_DATE (1 Apr 2026): whether the 1961 Act or the 2025 Act
  applies.

TAX YEAR FIRST, THEN REGIME -- the ordering matters and is easy to get wrong.
"When the question is asked" and "which tax year it concerns" are different
dates. Resolving the regime from today's date conflates them: a query asked in
July 2026 is past ACT_2025_EFFECTIVE_DATE, but the asker may be filing for
FY 2025-26 (AY 2026-27), which ENDED 31 Mar 2026 -- before the pivot -- so the
1961 Act governs. Deriving the regime from the wall clock would answer every
filing-season query under the wrong Act, with an authoritative-looking trace.

So: resolve the assessment year first (explicit if stated, else the most
recently completed FY -- the one being filed), then place as_of_date inside
that year, then compare against the pivots.

ANCHORED TO THE START OF THE RESOLVED FY (1 Apr), not the end. This matters
specifically for a FY that straddles CG_RATE_CHANGE_DATE (23 Jul 2024, inside
FY 2024-25): anchoring at the start reads as PRE_RATE_CHANGE, anchoring at the
end reads as POST_RATE_CHANGE, for the exact same "AY 2025-26" mention.
Deliberately consistent across every code path that resolves a year without an
exact date -- an explicit AY/FY mention and the "nothing stated, use the most
recently completed FY" default both use this same start-of-year anchor.
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

# "AY 2026-27" / "A.Y. 2026-27" / "assessment year 2026-27"
_AY_PATTERN = re.compile(
    r"\b(?:a\.?y\.?|assessment\s+year)\s*[:\-]?\s*(\d{4})\s*[-/]\s*(\d{2,4})\b",
    re.IGNORECASE,
)
# "FY 2025-26" / "F.Y. 2025-26" / "financial year 2025-26"
_FY_PATTERN = re.compile(
    r"\b(?:f\.?y\.?|financial\s+year)\s*[:\-]?\s*(\d{4})\s*[-/]\s*(\d{2,4})\b",
    re.IGNORECASE,
)
# ISO or common date formats, e.g. 2025-07-15, 15/07/2025, 15-07-2025
_DATE_PATTERN = re.compile(
    r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b|\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"
)


def _fy_label(start_year: int) -> str:
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def _ay_label(start_year: int) -> str:
    return f"{start_year + 1}-{str(start_year + 2)[-2:]}"


def _assessment_year_from_fy_start(start_year: int) -> AssessmentYear:
    return AssessmentYear(ay=_ay_label(start_year), financial_year=_fy_label(start_year))


def financial_year_start_for(as_of: date) -> int:
    """The FY a date falls inside. Indian FY runs 1 Apr -> 31 Mar."""
    return as_of.year if as_of.month >= 4 else as_of.year - 1


def most_recently_completed_fy_start(today: date) -> int:
    """The FY a taxpayer would currently be filing for.

    On 15 Jul 2026 this is FY 2025-26 (ended 31 Mar 2026), not the in-progress
    FY 2026-27 -- you file for a year after it ends.
    """
    return financial_year_start_for(today) - 1


def _parse_explicit_year(query: str) -> int | None:
    """FY start year stated in the query, via an AY or FY mention."""
    ay_match = _AY_PATTERN.search(query)
    if ay_match:
        return int(ay_match.group(1)) - 1

    fy_match = _FY_PATTERN.search(query)
    if fy_match:
        return int(fy_match.group(1))

    return None


def _parse_explicit_date(query: str) -> date | None:
    """An exact date stated in the query (not just an AY/FY mention)."""
    date_match = _DATE_PATTERN.search(query)
    if not date_match:
        return None

    if date_match.group(1):
        year, month, day = date_match.group(1), date_match.group(2), date_match.group(3)
    else:
        day, month, year = date_match.group(4), date_match.group(5), date_match.group(6)
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def resolve_as_of(
    query: str, explicit_date: date | None = None, today: date | None = None
) -> TaxYearContext:
    """Build the TaxYearContext every computation and retrieval carries.

    `explicit_date` is an as-of date supplied by the caller (the API's
    `as_of_date`); it takes precedence and is used verbatim. `today` is
    injectable so the resolution is testable without freezing the clock.
    """
    today = today or date.today()

    if explicit_date is not None:
        as_of_date = explicit_date
        fy_start = financial_year_start_for(explicit_date)
    else:
        fy_start = _parse_explicit_year(query)
        if fy_start is not None:
            # Anchor to the start of the stated FY -- see module docstring.
            as_of_date = date(fy_start, 4, 1)
        else:
            parsed_date = _parse_explicit_date(query)
            if parsed_date is not None:
                as_of_date = parsed_date
                fy_start = financial_year_start_for(parsed_date)
            else:
                fy_start = most_recently_completed_fy_start(today)
                as_of_date = date(fy_start, 4, 1)

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
        assessment_year=_assessment_year_from_fy_start(fy_start),
        regime=regime,
        capital_gains_period=capital_gains_period,
    )
