"""AY <-> Tax Year representation and the two hard-coded statutory pivot dates.

Every computation and every retrieval must resolve an as-of date/AY/regime FIRST.
This module is the single source of truth for the two pivot dates so that
services/query/temporal_resolver.py and services/computation/rules/capital_gains.py
never redefine them independently:

- 23 July 2024: capital gains rate/indexation change (Finance (No. 2) Act, 2024).
- 1 April 2026: transition from the Income-tax Act 1961 to the Income-tax Act 2025.
"""

from datetime import date
from enum import Enum

from pydantic import BaseModel

CG_RATE_CHANGE_DATE: date = date(2024, 7, 23)
ACT_2025_EFFECTIVE_DATE: date = date(2026, 4, 1)


class TaxActRegime(str, Enum):
    """Mirrors the `TaxActRegime` enum in prisma/schema.prisma."""

    ACT_1961 = "1961"
    ACT_2025 = "2025"


class CapitalGainsPeriod(str, Enum):
    """Which side of the 23-Jul-2024 rate/indexation change a transfer falls on."""

    PRE_RATE_CHANGE = "pre_2024_07_23"
    POST_RATE_CHANGE = "post_2024_07_23"


class AssessmentYear(BaseModel):
    """AY <-> Financial Year pairing, e.g. ay="2025-26", financial_year="2024-25"."""

    ay: str
    financial_year: str


class TaxYearContext(BaseModel):
    """The resolved temporal context that every computation/retrieval call carries.

    Produced by services/query/temporal_resolver.py and threaded through the
    orchestration graph state (see orchestration/state.py).
    """

    as_of_date: date
    assessment_year: AssessmentYear
    regime: TaxActRegime
    capital_gains_period: CapitalGainsPeriod
