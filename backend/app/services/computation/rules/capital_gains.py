"""Date-split capital gains computation: pre/post 23-Jul-2024 rate and
indexation change, including grandfathering for assets transferred after that
date but acquired before it. Pure function, zero I/O.

Rates (Finance (No. 2) Act, 2024): listed-equity LTCG 10% pre-change / 12.5%
post-change; other-asset LTCG 20% with indexation pre-change / 12.5% without
indexation post-change (with a grandfathering option to keep the pre-change
20%-with-indexation rate for assets acquired before the change); listed-
equity STCG 15% pre-change / 20% post-change. Holding-period thresholds:
>12 months for equity/listed securities, >24 months for other assets.

Where indexation actually applies (pre-change non-equity LTCG, or the
grandfathered post-change option), this function requires Cost Inflation
Index figures it does not receive as input -- it raises a specific exception
naming exactly what's missing rather than guessing an index multiplier.
Likewise, short-term gains on non-equity assets are taxed at the normal
income-tax slab rate, which this function also does not receive.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.shared.schemas.tax_year import CG_RATE_CHANGE_DATE, TaxYearContext

LTCG_EQUITY_RATE_PRE = Decimal("0.10")
LTCG_EQUITY_RATE_POST = Decimal("0.125")
LTCG_OTHER_RATE_POST = Decimal("0.125")  # without indexation
STCG_EQUITY_RATE_PRE = Decimal("0.15")
STCG_EQUITY_RATE_POST = Decimal("0.20")

EQUITY_LTCG_THRESHOLD_DAYS = 365
OTHER_LTCG_THRESHOLD_DAYS = 730


@dataclass(frozen=True)
class CapitalGainsInput:
    asset_class: str
    acquisition_date: date
    transfer_date: date
    full_value_consideration: Decimal
    cost_of_acquisition: Decimal
    cost_of_improvement: Decimal = Decimal("0")


@dataclass(frozen=True)
class CapitalGainsResult:
    gain_type: str  # "short_term" | "long_term"
    indexed_cost: Decimal | None
    taxable_gain: Decimal
    tax_rate_applied: Decimal
    tax_payable: Decimal
    grandfathered: bool


def _is_equity(asset_class: str) -> bool:
    lowered = asset_class.lower()
    return "equity" in lowered or "listed" in lowered


def compute_capital_gains(
    inputs: CapitalGainsInput, as_of: TaxYearContext
) -> CapitalGainsResult:
    if inputs.transfer_date < inputs.acquisition_date:
        raise ValueError("transfer_date cannot be before acquisition_date")
    if (
        inputs.full_value_consideration < 0
        or inputs.cost_of_acquisition < 0
        or inputs.cost_of_improvement < 0
    ):
        raise ValueError(
            "full_value_consideration, cost_of_acquisition, and "
            "cost_of_improvement cannot be negative"
        )

    is_equity = _is_equity(inputs.asset_class)
    holding_days = (inputs.transfer_date - inputs.acquisition_date).days
    threshold = EQUITY_LTCG_THRESHOLD_DAYS if is_equity else OTHER_LTCG_THRESHOLD_DAYS
    is_long_term = holding_days > threshold
    gain_type = "long_term" if is_long_term else "short_term"

    is_post_change = inputs.transfer_date >= CG_RATE_CHANGE_DATE
    grandfathered = (
        is_long_term
        and not is_equity
        and is_post_change
        and inputs.acquisition_date < CG_RATE_CHANGE_DATE
    )

    if is_long_term and not is_equity and (not is_post_change or grandfathered):
        raise ValueError(
            "Indexed cost of acquisition requires Cost Inflation Index (CII) "
            "values for the acquisition year and transfer year, which were "
            "not provided. Supply those CII figures to compute an indexed "
            "LTCG result for this pre-change or grandfathered case."
        )

    if not is_long_term and not is_equity:
        raise ValueError(
            "Short-term capital gains on non-equity assets are taxed at the "
            "taxpayer's normal income-tax slab rate, which was not provided. "
            "Supply the applicable slab rate to compute STCG tax payable."
        )

    total_cost = inputs.cost_of_acquisition + inputs.cost_of_improvement
    taxable_gain = max(
        (inputs.full_value_consideration - total_cost).quantize(Decimal("0.01")),
        Decimal("0.00"),
    )

    if is_long_term:
        rate = LTCG_EQUITY_RATE_POST if is_post_change else LTCG_EQUITY_RATE_PRE
        if not is_equity:
            rate = LTCG_OTHER_RATE_POST
    else:
        rate = STCG_EQUITY_RATE_POST if is_post_change else STCG_EQUITY_RATE_PRE

    tax_payable = (taxable_gain * rate).quantize(Decimal("0.01"))

    return CapitalGainsResult(
        gain_type=gain_type,
        indexed_cost=None,
        taxable_gain=taxable_gain,
        tax_rate_applied=rate,
        tax_payable=tax_payable,
        grandfathered=grandfathered,
    )
