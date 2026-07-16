"""Compares tax liability under Sec 115BAA/115BAB (concessional corporate tax
regimes, 1961 Act) against the normal-provisions rate, and flags whichever is
lower. Pure function, zero I/O.

Rates: 115BAA (any domestic company forgoing specified deductions) = 22%;
115BAB (new manufacturing companies) = 15%; both carry a flat 10% surcharge
(not slab-based) + 4% Health & Education Cess. Normal-provisions rate is
taken as 30% + slab-based surcharge (7% above Rs 1 crore, 12% above Rs 10
crore) + 4% cess -- the 25% concessional turnover-based rate is not modeled
here since RegimeComparisonInput does not carry a turnover figure. The
2025-Act equivalents are assumed rate-identical per public record of the
Act's restructuring, PENDING DOMAIN-EXPERT VERIFICATION once in force.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.shared.schemas.tax_year import TaxYearContext

NORMAL_REGIME_RATE = Decimal("0.30")
REGIME_115BAA_RATE = Decimal("0.22")
REGIME_115BAB_RATE = Decimal("0.15")
CONCESSIONAL_SURCHARGE_RATE = Decimal("0.10")
CESS_RATE = Decimal("0.04")
ONE_CRORE = Decimal("10000000")
TEN_CRORE = Decimal("100000000")


@dataclass(frozen=True)
class RegimeComparisonInput:
    total_income: Decimal
    is_new_manufacturing_company: bool


@dataclass(frozen=True)
class RegimeComparisonResult:
    old_regime_tax: Decimal
    new_regime_tax: Decimal
    recommended_regime: str


def _normal_regime_surcharge_rate(total_income: Decimal) -> Decimal:
    if total_income > TEN_CRORE:
        return Decimal("0.12")
    if total_income > ONE_CRORE:
        return Decimal("0.07")
    return Decimal("0.00")


def compare_regimes(
    inputs: RegimeComparisonInput, as_of: TaxYearContext
) -> RegimeComparisonResult:
    if inputs.total_income < 0:
        raise ValueError("total_income cannot be negative")

    old_base = inputs.total_income * NORMAL_REGIME_RATE
    old_surcharge = old_base * _normal_regime_surcharge_rate(inputs.total_income)
    old_regime_tax = ((old_base + old_surcharge) * (1 + CESS_RATE)).quantize(Decimal("0.01"))

    if inputs.is_new_manufacturing_company:
        new_rate = REGIME_115BAB_RATE
        concessional_section = "115BAB"
    else:
        new_rate = REGIME_115BAA_RATE
        concessional_section = "115BAA"

    new_base = inputs.total_income * new_rate
    new_surcharge = new_base * CONCESSIONAL_SURCHARGE_RATE
    new_regime_tax = ((new_base + new_surcharge) * (1 + CESS_RATE)).quantize(Decimal("0.01"))

    recommended_regime = concessional_section if new_regime_tax < old_regime_tax else "normal"

    return RegimeComparisonResult(
        old_regime_tax=old_regime_tax,
        new_regime_tax=new_regime_tax,
        recommended_regime=recommended_regime,
    )
