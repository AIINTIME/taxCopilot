"""Depreciation -- Schedule III (Companies Act) / Written Down Value method
under the Income-tax Act. Pure function, zero I/O.
"""

from dataclasses import dataclass

from app.shared.schemas.tax_year import TaxYearContext


@dataclass(frozen=True)
class DepreciationInput:
    opening_wdv: float
    additions: float
    disposals: float
    block_rate: float


@dataclass(frozen=True)
class DepreciationResult:
    depreciation_allowed: float
    closing_wdv: float


def compute_depreciation(
    inputs: DepreciationInput, as_of: TaxYearContext
) -> DepreciationResult:
    raise NotImplementedError(
        "TODO: implement Schedule III / WDV depreciation computation"
    )
