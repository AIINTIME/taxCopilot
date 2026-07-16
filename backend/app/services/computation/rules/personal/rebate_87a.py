"""Sec 87A rebate, with marginal relief where the regime provides it.
Pure function, zero I/O.

This is what zeroes low incomes: at a total income at or under the regime's
87A limit, the rebate cancels the slab tax outright. It is the reason a
5,00,000 income pays nil under BOTH regimes, and therefore the reason
regime_comparison_personal has to be able to report a tie.
"""

from app.services.computation.computation_trace import TraceStep
from app.services.computation.rules.personal.slab_tables import RegimeParams

SECTION = "Sec 87A"


def apply_rebate_87a(
    tax: float, total_income: float, params: RegimeParams
) -> tuple[float, list[TraceStep]]:
    """Return (tax after rebate, trace steps). Never returns a negative tax."""
    if tax <= 0:
        return 0.0, []

    if total_income <= params.rebate_87a_income_limit:
        rebate = min(tax, params.rebate_87a_max)
        return tax - rebate, [
            TraceStep(
                label=f"Rebate {SECTION}",
                amount=-rebate,
                section_reference=SECTION,
                detail=(
                    f"total income {total_income:,.0f} is within the "
                    f"{params.rebate_87a_income_limit:,.0f} limit; "
                    f"rebate capped at {params.rebate_87a_max:,.0f}"
                ),
            )
        ]

    if not params.rebate_87a_marginal_relief:
        return tax, []

    # Just above the limit, tax may not exceed the income above it.
    excess = total_income - params.rebate_87a_income_limit
    if tax <= excess:
        return tax, []

    relief = tax - excess
    return excess, [
        TraceStep(
            label=f"Marginal relief {SECTION}",
            amount=-relief,
            section_reference=SECTION,
            detail=(
                f"tax {tax:,.0f} exceeds income above the "
                f"{params.rebate_87a_income_limit:,.0f} limit ({excess:,.0f}); "
                f"capped at the excess"
            ),
        )
    ]
