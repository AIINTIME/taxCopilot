"""Piecewise slab tax on a taxable income. Pure function, zero I/O.

Rate-agnostic: every figure comes from the RegimeParams passed in, so this
module never needs editing when a Finance Act changes the slabs.
"""

from app.services.computation.computation_trace import TraceStep
from app.services.computation.rules.personal.slab_tables import RegimeParams


def _format_band(lower: float, upper: float | None) -> str:
    if upper is None:
        return f"Above {lower:,.0f}"
    return f"{lower:,.0f} to {upper:,.0f}"


def compute_slab_tax(
    taxable_income: float, params: RegimeParams
) -> tuple[float, list[TraceStep]]:
    """Return (tax before rebate/surcharge/cess, one TraceStep per taxed band).

    Nil-rate bands are not emitted as steps -- they contribute nothing and
    would only pad the shown working.
    """
    if taxable_income <= 0:
        return 0.0, []

    tax = 0.0
    steps: list[TraceStep] = []
    lower = 0.0

    for band in params.bands:
        if taxable_income <= lower:
            break

        ceiling = taxable_income if band.upper is None else min(band.upper, taxable_income)
        amount_in_band = ceiling - lower

        if amount_in_band > 0 and band.rate > 0:
            band_tax = amount_in_band * band.rate
            tax += band_tax
            steps.append(
                TraceStep(
                    label=f"Slab {_format_band(lower, band.upper)} @ {band.rate:.0%}",
                    amount=band_tax,
                    section_reference=params.slab_section,
                    detail=f"{amount_in_band:,.0f} taxed at {band.rate:.0%}",
                )
            )

        lower = ceiling if band.upper is None else band.upper

    return tax, steps
