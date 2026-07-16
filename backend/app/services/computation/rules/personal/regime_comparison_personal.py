"""Old vs new personal regime under Sec 115BAC. Pure function, zero I/O.

NOT to be confused with rules/regime_comparison.py, which compares the
concessional CORPORATE regimes of Sec 115BAA/115BAB. Different provision,
different taxpayer, different Act chapter. The names are similar; the
computations share nothing.

Two result fields carry more weight than they look:

  recommended = EITHER -- at low incomes the Sec 87A rebate zeroes BOTH
    regimes, and a tie is the correct answer. A bare string would silently
    resolve to whichever branch fell through first.

  breakeven_deductions -- when a taxpayer states an income but no deductions,
    the new regime "wins" only because nothing was claimed, not because there
    is nothing to claim. The decision-relevant figure is the deduction total
    at which the old regime overtakes. Without it the recommendation is
    technically correct and practically wrong for anyone with 80C plus HRA.
"""

from dataclasses import dataclass
from enum import Enum

from app.services.computation.computation_trace import TraceStep
from app.services.computation.rules.personal.deductions import (
    DeductionInputs,
    compute_deductions,
)
from app.services.computation.rules.personal.rebate_87a import apply_rebate_87a
from app.services.computation.rules.personal.slab_tables import (
    PersonalRegime,
    get_deduction_limits,
    get_params,
)
from app.services.computation.rules.personal.slab_tax import compute_slab_tax
from app.services.computation.rules.personal.surcharge_cess import (
    compute_cess,
    compute_surcharge,
)
from app.shared.schemas.tax_year import TaxYearContext

STATUTORY_REFERENCES = ["Sec 115BAC", "Sec 87A", "Sec 16(ia)"]

# Rupee tolerance below which the two regimes are treated as tied. Liability is
# rounded to the rupee, so anything under 1 is float noise, not a real delta.
_TIE_TOLERANCE = 1.0


class IncomeType(str, Enum):
    SALARY = "salary"
    BUSINESS = "business"
    OTHER = "other"


class RegimeRecommendation(str, Enum):
    OLD = "old"
    NEW = "new"
    EITHER = "either"


@dataclass(frozen=True)
class PersonalRegimeInput:
    gross_income: float
    income_type: IncomeType
    deductions: DeductionInputs = DeductionInputs()


@dataclass(frozen=True)
class RegimeOutcome:
    regime: PersonalRegime
    taxable_income: float
    total_tax: float
    steps: tuple[TraceStep, ...]
    disallowed_deductions: tuple[str, ...]
    capped_deductions: tuple[str, ...]


@dataclass(frozen=True)
class PersonalRegimeResult:
    old_regime_tax: float
    new_regime_tax: float
    delta: float
    recommended: RegimeRecommendation
    breakeven_deductions: float | None
    deciding_factors: tuple[str, ...]
    old_outcome: RegimeOutcome
    new_outcome: RegimeOutcome

    @property
    def steps(self) -> tuple[TraceStep, ...]:
        return self.new_outcome.steps if self.recommended is not RegimeRecommendation.OLD else self.old_outcome.steps


def compute_for_regime(
    inputs: PersonalRegimeInput, regime: PersonalRegime, as_of: TaxYearContext
) -> RegimeOutcome:
    ay = as_of.assessment_year.ay
    params = get_params(ay, regime)
    limits = get_deduction_limits(ay)

    steps: list[TraceStep] = [
        TraceStep(
            label="Gross income",
            amount=inputs.gross_income,
            section_reference=None,
            detail=inputs.income_type.value,
        )
    ]

    income = inputs.gross_income

    # The standard deduction is a salary deduction; business/other income does
    # not attract it under either regime.
    if inputs.income_type is IncomeType.SALARY and params.standard_deduction > 0:
        income -= params.standard_deduction
        steps.append(
            TraceStep(
                label="Standard deduction",
                amount=-params.standard_deduction,
                section_reference=params.standard_deduction_section,
                detail=f"{regime.value} regime",
            )
        )

    ded = compute_deductions(inputs.deductions, params, limits)
    income -= ded.total
    steps.extend(ded.steps)

    taxable = max(income, 0.0)
    steps.append(
        TraceStep(label="Taxable income", amount=taxable, section_reference=None)
    )

    tax, slab_steps = compute_slab_tax(taxable, params)
    steps.extend(slab_steps)

    tax, rebate_steps = apply_rebate_87a(tax, taxable, params)
    steps.extend(rebate_steps)

    surcharge, surcharge_steps = compute_surcharge(tax, taxable, params)
    steps.extend(surcharge_steps)

    cess, cess_steps = compute_cess(tax + surcharge, params)
    steps.extend(cess_steps)

    total = round(tax + surcharge + cess)
    steps.append(
        TraceStep(label="Total tax payable", amount=total, section_reference=None)
    )

    return RegimeOutcome(
        regime=regime,
        taxable_income=taxable,
        total_tax=total,
        steps=tuple(steps),
        disallowed_deductions=ded.disallowed,
        capped_deductions=ded.capped,
    )


def _solve_breakeven_deductions(
    inputs: PersonalRegimeInput, target_tax: float, as_of: TaxYearContext
) -> float | None:
    """Total additional old-regime deductions at which old-regime tax falls to
    `target_tax` (the new-regime liability).

    Old-regime tax is monotonically non-increasing in deductions, so bisect.
    Returns None when the old regime cannot reach the target even with the
    entire income deducted -- i.e. no deduction total makes it competitive.

    `extra` is priced straight against taxable income rather than routed
    through compute_deductions, because the question is "how much deduction in
    total", not "how much under which section" -- per-section caps would
    otherwise bound the search below the answer.
    """
    params = get_params(as_of.assessment_year.ay, PersonalRegime.OLD)

    income = inputs.gross_income
    if inputs.income_type is IncomeType.SALARY:
        income -= params.standard_deduction

    def old_tax_with(extra: float) -> float:
        taxable = max(income - extra, 0.0)
        tax, _ = compute_slab_tax(taxable, params)
        tax, _ = apply_rebate_87a(tax, taxable, params)
        surcharge, _ = compute_surcharge(tax, taxable, params)
        cess, _ = compute_cess(tax + surcharge, params)
        return round(tax + surcharge + cess)

    if old_tax_with(0.0) <= target_tax:
        return 0.0

    hi = inputs.gross_income
    if old_tax_with(hi) > target_tax:
        return None

    lo = 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if old_tax_with(mid) > target_tax:
            lo = mid
        else:
            hi = mid

    return round(hi)


def compare_regimes_personal(
    inputs: PersonalRegimeInput, as_of: TaxYearContext
) -> PersonalRegimeResult:
    old = compute_for_regime(inputs, PersonalRegime.OLD, as_of)
    new = compute_for_regime(inputs, PersonalRegime.NEW, as_of)

    delta = old.total_tax - new.total_tax

    if abs(delta) < _TIE_TOLERANCE:
        recommended = RegimeRecommendation.EITHER
    elif delta > 0:
        recommended = RegimeRecommendation.NEW
    else:
        recommended = RegimeRecommendation.OLD

    factors: list[str] = []
    if recommended is RegimeRecommendation.EITHER:
        if old.total_tax == 0:
            factors.append(
                "Both regimes give nil tax at this income after the Sec 87A rebate"
            )
        else:
            factors.append("Both regimes give the same liability at this income")
    elif recommended is RegimeRecommendation.NEW:
        factors.append(
            f"New regime's wider slabs outweigh the deductions it forfeits "
            f"(saves {abs(delta):,.0f})"
        )
        if new.disallowed_deductions:
            factors.append(
                "New regime disallows: " + ", ".join(new.disallowed_deductions)
            )
    else:
        factors.append(
            f"Old regime's deductions outweigh the new regime's wider slabs "
            f"(saves {abs(delta):,.0f})"
        )
    if old.capped_deductions:
        factors.append("Claims capped at statutory limits: " + ", ".join(old.capped_deductions))

    breakeven = (
        _solve_breakeven_deductions(inputs, new.total_tax, as_of)
        if recommended is RegimeRecommendation.NEW
        else None
    )

    return PersonalRegimeResult(
        old_regime_tax=old.total_tax,
        new_regime_tax=new.total_tax,
        delta=delta,
        recommended=recommended,
        breakeven_deductions=breakeven,
        deciding_factors=tuple(factors),
        old_outcome=old,
        new_outcome=new,
    )
