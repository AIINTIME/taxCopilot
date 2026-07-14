"""Compares tax liability under Sec 115BAA/115BAB (concessional corporate tax
regimes, 1961 Act) against their Income-tax Act 2025 equivalents. Pure
function, zero I/O.
"""

from dataclasses import dataclass

from app.shared.schemas.tax_year import TaxYearContext


@dataclass(frozen=True)
class RegimeComparisonInput:
    total_income: float
    is_new_manufacturing_company: bool


@dataclass(frozen=True)
class RegimeComparisonResult:
    old_regime_tax: float
    new_regime_tax: float
    recommended_regime: str


def compare_regimes(
    inputs: RegimeComparisonInput, as_of: TaxYearContext
) -> RegimeComparisonResult:
    raise NotImplementedError(
        "TODO: implement Sec 115BAA/115BAB vs 2025-Act equivalent comparison"
    )
