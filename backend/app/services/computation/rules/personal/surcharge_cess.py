"""Surcharge (with marginal relief) and Health & Education cess.
Pure functions, zero I/O.

Surcharge is a cliff, not a slab: crossing a threshold applies the rate to the
WHOLE tax, not just the excess. Marginal relief exists precisely to stop a
rupee of extra income costing thousands in tax, and omitting it overstates
liability at every threshold -- so it is computed here, not left to the caller.
"""

from app.services.computation.computation_trace import TraceStep
from app.services.computation.rules.personal.slab_tables import RegimeParams

SURCHARGE_SECTION = "Surcharge (Finance Act, First Schedule)"
CESS_SECTION = "Health and Education Cess"


def _surcharge_rate(total_income: float, params: RegimeParams) -> float:
    for band in params.surcharge_bands:
        if band.upper is None or total_income <= band.upper:
            return band.rate
    return params.surcharge_bands[-1].rate


def _threshold_below(total_income: float, params: RegimeParams) -> float | None:
    """The surcharge threshold this income sits just above, if any."""
    crossed = [
        b.upper
        for b in params.surcharge_bands
        if b.upper is not None and total_income > b.upper
    ]
    return max(crossed) if crossed else None


def compute_surcharge(
    tax: float, total_income: float, params: RegimeParams
) -> tuple[float, list[TraceStep]]:
    rate = _surcharge_rate(total_income, params)
    if rate <= 0 or tax <= 0:
        return 0.0, []

    surcharge = tax * rate
    steps = [
        TraceStep(
            label=f"Surcharge @ {rate:.0%}",
            amount=surcharge,
            section_reference=SURCHARGE_SECTION,
            detail=f"total income {total_income:,.0f}",
        )
    ]

    threshold = _threshold_below(total_income, params)
    if threshold is None:
        return surcharge, steps

    # Marginal relief: (tax + surcharge) may not exceed the tax at the
    # threshold plus the whole of the income above it.
    tax_at_threshold = _tax_at_threshold(threshold, params)
    ceiling = tax_at_threshold + (total_income - threshold)
    if tax + surcharge <= ceiling:
        return surcharge, steps

    relieved = max(ceiling - tax, 0.0)
    steps.append(
        TraceStep(
            label="Marginal relief on surcharge",
            amount=relieved - surcharge,
            section_reference=SURCHARGE_SECTION,
            detail=(
                f"tax plus surcharge capped at tax on {threshold:,.0f} "
                f"plus income above it"
            ),
        )
    )
    return relieved, steps


def _tax_at_threshold(threshold: float, params: RegimeParams) -> float:
    """Slab tax on exactly the threshold income, ignoring surcharge.

    Imported lazily to keep slab_tax free to import this module's siblings
    without a cycle.
    """
    from app.services.computation.rules.personal.slab_tax import compute_slab_tax

    tax, _ = compute_slab_tax(threshold, params)
    return tax


def compute_cess(
    tax_plus_surcharge: float, params: RegimeParams
) -> tuple[float, list[TraceStep]]:
    if tax_plus_surcharge <= 0:
        return 0.0, []

    cess = tax_plus_surcharge * params.cess_rate
    return cess, [
        TraceStep(
            label=f"Health and Education Cess @ {params.cess_rate:.0%}",
            amount=cess,
            section_reference=CESS_SECTION,
            detail="charged on tax plus surcharge",
        )
    ]
