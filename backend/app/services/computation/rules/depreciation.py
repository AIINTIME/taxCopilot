"""Depreciation -- Schedule III (Companies Act) / Written Down Value method
under the Income-tax Act. Pure function, zero I/O.

Note: the WDV method applies half the block rate to additions used for
fewer than 180 days in the year of acquisition. DepreciationInput does not
carry a per-addition usage-days figure, so this function applies the full
block rate to all additions -- a deliberate scope boundary (not a silent
assumption): a caller needing the 180-day split must supply that separately.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.shared.schemas.tax_year import TaxYearContext


@dataclass(frozen=True)
class DepreciationInput:
    opening_wdv: Decimal
    additions: Decimal
    disposals: Decimal
    block_rate: Decimal


@dataclass(frozen=True)
class DepreciationResult:
    depreciation_allowed: Decimal
    closing_wdv: Decimal


def compute_depreciation(
    inputs: DepreciationInput, as_of: TaxYearContext
) -> DepreciationResult:
    if inputs.opening_wdv < 0 or inputs.additions < 0 or inputs.disposals < 0:
        raise ValueError("opening_wdv, additions, and disposals cannot be negative")
    if not (Decimal("0") <= inputs.block_rate <= Decimal("1")):
        raise ValueError("block_rate must be expressed as a fraction between 0 and 1")

    depreciable_base = inputs.opening_wdv + inputs.additions - inputs.disposals
    if depreciable_base < 0:
        raise ValueError(
            "disposals exceed opening_wdv plus additions -- block balance cannot go negative"
        )

    depreciation_allowed = (depreciable_base * inputs.block_rate).quantize(Decimal("0.01"))
    closing_wdv = depreciable_base - depreciation_allowed

    return DepreciationResult(
        depreciation_allowed=depreciation_allowed, closing_wdv=closing_wdv
    )
