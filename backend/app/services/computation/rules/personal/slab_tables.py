"""Versioned personal income-tax rate data, keyed by (assessment year, regime).

Static reference data, not a rule -- same role and pattern as cii_tables.py:
pure, zero I/O, and the single place a rate may appear. Rate literals must
never be written into rule logic; every rule reads them from here so that a
Finance Act change is a data edit, not a code change.

TWO UNRELATED MEANINGS OF "REGIME" -- do not conflate:
  - TaxActRegime (shared/schemas/tax_year.py): ACT_1961 vs ACT_2025, i.e.
    WHICH ACT governs, pivoting on 1 Apr 2026.
  - PersonalRegime (here): OLD vs NEW, i.e. which slab scheme under
    Sec 115BAC an individual elects. Orthogonal to the above.

SCOPE: individuals below 60 only. Senior (60+) and super-senior (80+) old
regime slabs use higher basic exemptions and are not yet seeded; get_params
raises rather than silently returning the below-60 table for them.

SOURCES -- figures below are transcribed from the Income Tax Department's
published rates for AY 2026-27 (Finance Act, 2025), retrieved 2026-07-15:
  https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1
  https://www.incometaxindia.gov.in/w/deductions-allowable-to-tax-payer
Re-verify against the bare Act before relying on these in production, and add
a new (ay, regime) entry per Finance Act rather than editing an existing one --
prior years must stay reproducible for audit.
"""

from dataclasses import dataclass
from enum import Enum


class PersonalRegime(str, Enum):
    """Which Sec 115BAC slab scheme an individual elects."""

    OLD = "old"
    NEW = "new"


@dataclass(frozen=True)
class SlabBand:
    """A band is taxed at `rate` on income between the previous band's upper
    bound and this one. `upper=None` marks the final, open-ended band.
    """

    upper: float | None
    rate: float


@dataclass(frozen=True)
class SurchargeBand:
    upper: float | None
    rate: float


@dataclass(frozen=True)
class RegimeParams:
    bands: tuple[SlabBand, ...]
    surcharge_bands: tuple[SurchargeBand, ...]
    standard_deduction: float
    rebate_87a_income_limit: float
    rebate_87a_max: float
    rebate_87a_marginal_relief: bool
    """Whether marginal relief caps tax at the excess over the 87A income limit
    for incomes just above it. Available under Sec 115BAC; not under the old
    regime, where crossing the limit forfeits the rebate outright.
    """
    cess_rate: float
    slab_section: str
    standard_deduction_section: str
    source_reference: str
    allowed_deductions: frozenset[str]
    """Chapter VI-A / other deductions this regime permits, by DeductionInputs
    field name. Which deductions survive an election under Sec 115BAC is a
    statutory fact that Finance Acts amend, so it is data here rather than a
    branch in deductions.py. The standard deduction is not listed -- it is
    available under both regimes and is carried by `standard_deduction`.
    """


@dataclass(frozen=True)
class DeductionLimits:
    """Statutory caps, by DeductionInputs field name. Uncapped entries are absent."""

    section_80c: float
    section_80d_self: float
    section_80d_parents_senior: float
    section_80tta: float
    home_loan_interest_24b: float
    source_reference: str


_CESS_RATE = 0.04
_CESS_SECTION = "Health and Education Cess @ 4%"

# Surcharge thresholds are common to both regimes except the top band, which
# the new regime caps at 25% against the old regime's 37%.
_SURCHARGE_COMMON = (
    SurchargeBand(upper=5_000_000, rate=0.0),
    SurchargeBand(upper=10_000_000, rate=0.10),
    SurchargeBand(upper=20_000_000, rate=0.15),
    SurchargeBand(upper=50_000_000, rate=0.25),
)

# Electing Sec 115BAC forfeits most Chapter VI-A deductions; employer NPS
# contribution under Sec 80CCD(2) is among the few that survive.
_NEW_REGIME_ALLOWED = frozenset({"employer_nps_80ccd2"})
_OLD_REGIME_ALLOWED = frozenset(
    {
        "section_80c",
        "section_80d",
        "section_80g",
        "section_80tta",
        "home_loan_interest_24b",
        "hra_exemption",
        "employer_nps_80ccd2",
    }
)

SLABS: dict[tuple[str, PersonalRegime], RegimeParams] = {
    ("2026-27", PersonalRegime.NEW): RegimeParams(
        bands=(
            SlabBand(upper=400_000, rate=0.0),
            SlabBand(upper=800_000, rate=0.05),
            SlabBand(upper=1_200_000, rate=0.10),
            SlabBand(upper=1_600_000, rate=0.15),
            SlabBand(upper=2_000_000, rate=0.20),
            SlabBand(upper=2_400_000, rate=0.25),
            SlabBand(upper=None, rate=0.30),
        ),
        surcharge_bands=_SURCHARGE_COMMON + (SurchargeBand(upper=None, rate=0.25),),
        standard_deduction=75_000,
        rebate_87a_income_limit=1_200_000,
        rebate_87a_max=60_000,
        rebate_87a_marginal_relief=True,
        cess_rate=_CESS_RATE,
        slab_section="Sec 115BAC(1A)",
        standard_deduction_section="Sec 16(ia)",
        source_reference="Finance Act, 2025 -- rates for AY 2026-27",
        allowed_deductions=_NEW_REGIME_ALLOWED,
    ),
    ("2026-27", PersonalRegime.OLD): RegimeParams(
        bands=(
            SlabBand(upper=250_000, rate=0.0),
            SlabBand(upper=500_000, rate=0.05),
            SlabBand(upper=1_000_000, rate=0.20),
            SlabBand(upper=None, rate=0.30),
        ),
        surcharge_bands=_SURCHARGE_COMMON + (SurchargeBand(upper=None, rate=0.37),),
        standard_deduction=50_000,
        rebate_87a_income_limit=500_000,
        rebate_87a_max=12_500,
        rebate_87a_marginal_relief=False,
        cess_rate=_CESS_RATE,
        slab_section="Sec 2(1) r/w First Schedule, Part I",
        standard_deduction_section="Sec 16(ia)",
        source_reference="Finance Act, 2025 -- rates for AY 2026-27",
        allowed_deductions=_OLD_REGIME_ALLOWED,
    ),
}

DEDUCTION_LIMITS: dict[str, DeductionLimits] = {
    "2026-27": DeductionLimits(
        section_80c=150_000,
        section_80d_self=25_000,
        section_80d_parents_senior=50_000,
        section_80tta=10_000,
        home_loan_interest_24b=200_000,
        source_reference="Income-tax Act, 1961 -- Chapter VI-A limits, AY 2026-27",
    ),
}


class RatesNotSeededError(LookupError):
    """Raised when no rate table exists for the requested year/regime.

    Deliberately fatal: guessing or falling back to an adjacent year's rates
    would produce a confidently wrong figure, which is worse than no answer.
    """


def get_params(assessment_year: str, regime: PersonalRegime) -> RegimeParams:
    try:
        return SLABS[(assessment_year, regime)]
    except KeyError:
        seeded = sorted({ay for ay, _ in SLABS})
        raise RatesNotSeededError(
            f"No {regime.value}-regime rates seeded for AY {assessment_year}. "
            f"Seeded years: {seeded or 'none'}. Add them to SLABS from the "
            f"relevant Finance Act -- do not infer them from an adjacent year."
        ) from None


def get_deduction_limits(assessment_year: str) -> DeductionLimits:
    try:
        return DEDUCTION_LIMITS[assessment_year]
    except KeyError:
        raise RatesNotSeededError(
            f"No deduction limits seeded for AY {assessment_year}. "
            f"Seeded years: {sorted(DEDUCTION_LIMITS) or 'none'}."
        ) from None
