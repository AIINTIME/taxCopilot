"""Date-split capital gains computation: pre/post 23-Jul-2024 rate and
indexation change, including grandfathering for assets transferred after that
date but acquired before it. Pure function, zero I/O.

Must branch on CG_RATE_CHANGE_DATE (app.shared.schemas.tax_year) -- this is
one of the two hard-coded pivot dates the whole system resolves as-of first.
"""

from dataclasses import dataclass
from datetime import date

from app.shared.schemas.tax_year import TaxYearContext


@dataclass(frozen=True)
class CapitalGainsInput:
    asset_class: str
    acquisition_date: date
    transfer_date: date
    full_value_consideration: float
    cost_of_acquisition: float
    cost_of_improvement: float = 0.0


@dataclass(frozen=True)
class CapitalGainsResult:
    gain_type: str  # "short_term" | "long_term"
    indexed_cost: float | None
    taxable_gain: float
    tax_rate_applied: float
    tax_payable: float
    grandfathered: bool


def compute_capital_gains(
    inputs: CapitalGainsInput, as_of: TaxYearContext
) -> CapitalGainsResult:
    raise NotImplementedError(
        "TODO: branch on CG_RATE_CHANGE_DATE (23-Jul-2024) using "
        "inputs.transfer_date to select pre/post rate & indexation rules, "
        "and apply grandfathering where acquisition_date predates the change"
    )
