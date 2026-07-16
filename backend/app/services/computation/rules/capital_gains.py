"""Date-split capital gains computation: pre/post 23-Jul-2024 rate and
indexation change, including grandfathering for assets transferred after that
date but acquired before it. Pure function, zero I/O.

Must branch on CG_RATE_CHANGE_DATE (app.shared.schemas.tax_year) -- this is
one of the two hard-coded pivot dates the whole system resolves as-of first.
Branches on `inputs.transfer_date` directly (not `as_of`, which instead
governs which Act's sections get cited in the computation trace).

Asset classes (kept as a free string on CapitalGainsInput, matching the
existing schema):
  - "listed_equity_or_equity_mf" -- STT-paid listed equity shares / equity-
    oriented mutual funds / business trust units. Sec 111A (STCG) / 112A
    (LTCG). 12-month long-term threshold. Never indexed.
  - anything else ("other") -- immovable property, unlisted shares, and
    other capital assets. Sec 112. 24-month long-term threshold.

Documented simplifications (see plan / user-confirmed decisions):
  - No separate "expenditure on transfer" input -- cost_of_acquisition +
    cost_of_improvement is treated as the full deductible cost base.
  - cost_of_improvement is indexed using the acquisition year's CII (the
    input has no separate improvement date).
  - The Sec 112 grandfathering choice (20% w/ indexation vs 12.5% w/o) is
    applied to ANY "other"-class asset acquired pre-change and transferred
    post-change, not restricted to resident individuals/HUFs on land/
    building as the literal statute provides -- no taxpayer-type field
    exists on this input by design.
  - The Sec 112A LTCG exemption threshold (Rs 1L / Rs 1.25L) is applied per
    computation call, not aggregated across a taxpayer's other 112A
    transactions in the year.
"""

import calendar
from dataclasses import dataclass
from datetime import date

from app.services.computation.cii_tables import get_cii
from app.shared.schemas.tax_year import CG_RATE_CHANGE_DATE, TaxYearContext

LISTED_EQUITY_OR_EQUITY_MF = "listed_equity_or_equity_mf"

_LISTED_LT_THRESHOLD_MONTHS = 12
_OTHER_LT_THRESHOLD_MONTHS = 24

_STCG_111A_RATE_PRE = 0.15
_STCG_111A_RATE_POST = 0.20

_LTCG_112A_RATE_PRE = 0.10
_LTCG_112A_RATE_POST = 0.125
_LTCG_112A_EXEMPTION_PRE = 100_000.0
_LTCG_112A_EXEMPTION_POST = 125_000.0

_LTCG_112_RATE_WITH_INDEXATION = 0.20
_LTCG_112_RATE_WITHOUT_INDEXATION = 0.125


@dataclass(frozen=True)
class CapitalGainsInput:
    asset_class: str
    acquisition_date: date
    transfer_date: date
    full_value_consideration: float
    cost_of_acquisition: float
    cost_of_improvement: float = 0.0
    # Required only when the computed gain is STCG on a non-111A ("other")
    # asset: Sec 111A/112/112A give no fixed rate for that case -- by
    # statute it's taxed at the assessee's normal/slab rate, which this pure
    # function cannot know on its own.
    applicable_slab_rate: float | None = None


@dataclass(frozen=True)
class CapitalGainsResult:
    gain_type: str  # "short_term" | "long_term"
    indexed_cost: float | None
    taxable_gain: float
    tax_rate_applied: float
    tax_payable: float
    grandfathered: bool


def _financial_year(d: date) -> str:
    """Indian FY (Apr-Mar) string for `d`, e.g. date(2024, 8, 1) -> "2024-25"."""
    start_year = d.year if d.month >= 4 else d.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def _add_months(d: date, months: int) -> date:
    total_month_index = d.month - 1 + months
    year = d.year + total_month_index // 12
    month = total_month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _is_long_term(asset_class: str, acquisition_date: date, transfer_date: date) -> bool:
    threshold_months = (
        _LISTED_LT_THRESHOLD_MONTHS
        if asset_class == LISTED_EQUITY_OR_EQUITY_MF
        else _OTHER_LT_THRESHOLD_MONTHS
    )
    return transfer_date > _add_months(acquisition_date, threshold_months)


def _indexed_cost(
    cost_of_acquisition: float,
    cost_of_improvement: float,
    acquisition_date: date,
    transfer_date: date,
) -> float:
    ratio = get_cii(_financial_year(transfer_date)) / get_cii(_financial_year(acquisition_date))
    return (cost_of_acquisition + cost_of_improvement) * ratio


def compute_capital_gains(
    inputs: CapitalGainsInput, as_of: TaxYearContext
) -> CapitalGainsResult:
    is_long_term = _is_long_term(
        inputs.asset_class, inputs.acquisition_date, inputs.transfer_date
    )
    gain_type = "long_term" if is_long_term else "short_term"
    cost_base = inputs.cost_of_acquisition + inputs.cost_of_improvement
    pre_change = inputs.transfer_date < CG_RATE_CHANGE_DATE

    if inputs.asset_class == LISTED_EQUITY_OR_EQUITY_MF:
        gross_gain = max(inputs.full_value_consideration - cost_base, 0.0)
        if not is_long_term:
            rate = _STCG_111A_RATE_PRE if pre_change else _STCG_111A_RATE_POST
            return CapitalGainsResult(
                gain_type=gain_type,
                indexed_cost=None,
                taxable_gain=gross_gain,
                tax_rate_applied=rate,
                tax_payable=gross_gain * rate,
                grandfathered=False,
            )

        exemption = _LTCG_112A_EXEMPTION_PRE if pre_change else _LTCG_112A_EXEMPTION_POST
        rate = _LTCG_112A_RATE_PRE if pre_change else _LTCG_112A_RATE_POST
        taxable_gain = max(gross_gain - exemption, 0.0)
        return CapitalGainsResult(
            gain_type=gain_type,
            indexed_cost=None,
            taxable_gain=taxable_gain,
            tax_rate_applied=rate,
            tax_payable=taxable_gain * rate,
            grandfathered=False,
        )

    # "other" asset class -- Sec 112
    if not is_long_term:
        if inputs.applicable_slab_rate is None:
            raise ValueError(
                "applicable_slab_rate is required to compute tax on short-term "
                "capital gains for a non-Sec-111A asset class -- Sec 111A does "
                "not apply, and no other fixed capital-gains rate exists for "
                "this case; the Act taxes it at the assessee's normal/slab rate"
            )
        gross_gain = max(inputs.full_value_consideration - cost_base, 0.0)
        rate = inputs.applicable_slab_rate
        return CapitalGainsResult(
            gain_type=gain_type,
            indexed_cost=None,
            taxable_gain=gross_gain,
            tax_rate_applied=rate,
            tax_payable=gross_gain * rate,
            grandfathered=False,
        )

    # Long-term, "other" asset class
    if pre_change:
        indexed_cost = _indexed_cost(
            inputs.cost_of_acquisition,
            inputs.cost_of_improvement,
            inputs.acquisition_date,
            inputs.transfer_date,
        )
        taxable_gain = max(inputs.full_value_consideration - indexed_cost, 0.0)
        return CapitalGainsResult(
            gain_type=gain_type,
            indexed_cost=indexed_cost,
            taxable_gain=taxable_gain,
            tax_rate_applied=_LTCG_112_RATE_WITH_INDEXATION,
            tax_payable=taxable_gain * _LTCG_112_RATE_WITH_INDEXATION,
            grandfathered=False,
        )

    # Post-change, long-term, "other" asset class
    gain_without_indexation = max(inputs.full_value_consideration - cost_base, 0.0)
    tax_without_indexation = gain_without_indexation * _LTCG_112_RATE_WITHOUT_INDEXATION

    if inputs.acquisition_date >= CG_RATE_CHANGE_DATE:
        # Acquired on/after the change date -- no grandfathering choice available.
        return CapitalGainsResult(
            gain_type=gain_type,
            indexed_cost=None,
            taxable_gain=gain_without_indexation,
            tax_rate_applied=_LTCG_112_RATE_WITHOUT_INDEXATION,
            tax_payable=tax_without_indexation,
            grandfathered=False,
        )

    # Grandfathering comparison: acquired pre-change, transferred post-change.
    indexed_cost = _indexed_cost(
        inputs.cost_of_acquisition,
        inputs.cost_of_improvement,
        inputs.acquisition_date,
        inputs.transfer_date,
    )
    gain_with_indexation = max(inputs.full_value_consideration - indexed_cost, 0.0)
    tax_with_indexation = gain_with_indexation * _LTCG_112_RATE_WITH_INDEXATION

    if tax_with_indexation < tax_without_indexation:
        return CapitalGainsResult(
            gain_type=gain_type,
            indexed_cost=indexed_cost,
            taxable_gain=gain_with_indexation,
            tax_rate_applied=_LTCG_112_RATE_WITH_INDEXATION,
            tax_payable=tax_with_indexation,
            grandfathered=True,
        )

    return CapitalGainsResult(
        gain_type=gain_type,
        indexed_cost=None,
        taxable_gain=gain_without_indexation,
        tax_rate_applied=_LTCG_112_RATE_WITHOUT_INDEXATION,
        tax_payable=tax_without_indexation,
        grandfathered=True,
    )
