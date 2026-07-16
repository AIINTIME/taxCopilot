"""Capital gains reinvestment exemptions -- Sec 54 (residential house ->
residential house), 54B (agricultural land -> agricultural land), 54EC
(land/building -> specified bonds), 54F (any LT asset other than a house ->
one residential house). Pure function, zero I/O -- same "one statutory
computation per rule file" pattern as rules/capital_gains.py.

Eligibility facts this function cannot itself derive (e.g. "was the land
used for agriculture for 2 years prior", "does the assessee own another
house") are supplied by the caller as booleans -- never inferred here.

Documented simplifications:
  - The Sec 54/54F reinvestment timing window (1 yr before / 2 yr after for
    purchase, 3 yr after for construction) is collapsed into a single
    [-1yr, +3yr] window around transfer_date, since this input has no
    separate purchase-vs-construction flag.
  - `cgas_deposit_required` is a simplified check: True only when the
    reinvestment happens after the transfer date and the caller confirms it
    was not deposited into the Capital Gains Account Scheme by the return
    due date -- the real due-date computation is out of scope.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.shared.schemas.tax_year import TaxYearContext

ExemptionSection = Literal["54", "54B", "54EC", "54F"]

_SEC_54_INVESTMENT_CAP = 10_00_00_000.0  # Rs 10 crore, Finance Act 2023
_SEC_54F_INVESTMENT_CAP = 10_00_00_000.0  # Rs 10 crore, Finance Act 2023
_SEC_54EC_INVESTMENT_CAP = 50_00_000.0  # Rs 50 lakh
_SEC_54EC_WINDOW_DAYS = 183  # ~6 months
_SEC_54B_WINDOW_DAYS = 2 * 365
_HOUSE_WINDOW_BEFORE_DAYS = 365
_HOUSE_WINDOW_AFTER_DAYS = 3 * 365


@dataclass(frozen=True)
class ExemptionInput:
    section: ExemptionSection
    capital_gain: float
    cost_of_new_asset: float
    investment_date: date
    transfer_date: date
    net_consideration: float | None = None  # required for Sec 54F's proportionate formula
    amount_utilized_or_deposited_by_due_date: bool = True
    # Sec 54F only: assessee must not own >1 other residential house on the transfer date.
    owns_more_than_one_other_residential_house: bool = False
    # Sec 54B only: the land must have been used for agriculture for 2 years prior.
    land_used_for_agriculture_two_years_prior: bool = True
    # Sec 54EC only: the asset transferred must be land or building.
    original_asset_is_land_or_building: bool = True


@dataclass(frozen=True)
class ExemptionResult:
    exemption_amount: float
    taxable_gain_after_exemption: float
    conditions_met: bool
    cgas_deposit_required: bool
    notes: list[str]


def _within_window(investment_date: date, transfer_date: date, before_days: int, after_days: int) -> bool:
    return (
        transfer_date - timedelta(days=before_days)
        <= investment_date
        <= transfer_date + timedelta(days=after_days)
    )


def compute_exemption(inputs: ExemptionInput, as_of: TaxYearContext) -> ExemptionResult:
    notes: list[str] = []
    conditions_met = True

    if inputs.section == "54":
        if not _within_window(
            inputs.investment_date, inputs.transfer_date,
            _HOUSE_WINDOW_BEFORE_DAYS, _HOUSE_WINDOW_AFTER_DAYS,
        ):
            conditions_met = False
            notes.append(
                "Investment date is outside the Sec 54 window (1 yr before to "
                "3 yr after transfer)"
            )
        eligible_investment = inputs.cost_of_new_asset
        if eligible_investment > _SEC_54_INVESTMENT_CAP:
            notes.append(f"Investment capped at Rs {_SEC_54_INVESTMENT_CAP:,.0f} (Sec 54 cap)")
            eligible_investment = _SEC_54_INVESTMENT_CAP
        exemption_amount = min(inputs.capital_gain, eligible_investment) if conditions_met else 0.0

    elif inputs.section == "54B":
        if not inputs.land_used_for_agriculture_two_years_prior:
            conditions_met = False
            notes.append("Land was not used for agricultural purposes for 2 years prior to transfer")
        if not _within_window(inputs.investment_date, inputs.transfer_date, 0, _SEC_54B_WINDOW_DAYS):
            conditions_met = False
            notes.append("Investment date is outside the Sec 54B window (within 2 yr after transfer)")
        exemption_amount = min(inputs.capital_gain, inputs.cost_of_new_asset) if conditions_met else 0.0

    elif inputs.section == "54EC":
        if not inputs.original_asset_is_land_or_building:
            conditions_met = False
            notes.append("Sec 54EC applies only where the transferred asset is land or building")
        if not _within_window(inputs.investment_date, inputs.transfer_date, 0, _SEC_54EC_WINDOW_DAYS):
            conditions_met = False
            notes.append("Investment date is outside the Sec 54EC window (within 6 months of transfer)")
        eligible_investment = inputs.cost_of_new_asset
        if eligible_investment > _SEC_54EC_INVESTMENT_CAP:
            notes.append(f"Investment capped at Rs {_SEC_54EC_INVESTMENT_CAP:,.0f} (Sec 54EC cap)")
            eligible_investment = _SEC_54EC_INVESTMENT_CAP
        exemption_amount = min(inputs.capital_gain, eligible_investment) if conditions_met else 0.0

    elif inputs.section == "54F":
        if inputs.owns_more_than_one_other_residential_house:
            conditions_met = False
            notes.append(
                "Sec 54F is disallowed: assessee owns more than one other "
                "residential house on the date of transfer"
            )
        if not _within_window(
            inputs.investment_date, inputs.transfer_date,
            _HOUSE_WINDOW_BEFORE_DAYS, _HOUSE_WINDOW_AFTER_DAYS,
        ):
            conditions_met = False
            notes.append(
                "Investment date is outside the Sec 54F window (1 yr before to "
                "3 yr after transfer)"
            )
        if inputs.net_consideration is None or inputs.net_consideration <= 0:
            raise ValueError("net_consideration is required and must be positive for Sec 54F")

        eligible_investment = min(inputs.cost_of_new_asset, _SEC_54F_INVESTMENT_CAP)
        if inputs.cost_of_new_asset > _SEC_54F_INVESTMENT_CAP:
            notes.append(f"Investment capped at Rs {_SEC_54F_INVESTMENT_CAP:,.0f} (Sec 54F cap)")

        if not conditions_met:
            exemption_amount = 0.0
        elif eligible_investment >= inputs.net_consideration:
            exemption_amount = inputs.capital_gain
        else:
            exemption_amount = min(
                inputs.capital_gain,
                inputs.capital_gain * eligible_investment / inputs.net_consideration,
            )

    else:
        raise ValueError(f"Unknown exemption section: {inputs.section!r}")

    exemption_amount = max(0.0, min(exemption_amount, inputs.capital_gain))
    taxable_gain_after_exemption = inputs.capital_gain - exemption_amount

    cgas_deposit_required = (
        conditions_met
        and inputs.investment_date > inputs.transfer_date
        and not inputs.amount_utilized_or_deposited_by_due_date
    )
    if cgas_deposit_required:
        notes.append(
            "Reinvestment occurred after transfer and was not confirmed deposited "
            "in the Capital Gains Account Scheme by the return due date -- "
            "exemption is at risk unless deposited"
        )

    return ExemptionResult(
        exemption_amount=exemption_amount,
        taxable_gain_after_exemption=taxable_gain_after_exemption,
        conditions_met=conditions_met,
        cgas_deposit_required=cgas_deposit_required,
        notes=notes,
    )
