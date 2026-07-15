"""Recompute a filed return from its own declared inputs and diff the result
against what was declared. Pure function, zero I/O.

The method is deliberately narrow: take the taxpayer's stated income and
deductions, run them through the same engine that answers "what do I owe"
(computation/rules/personal), and compare. Any gap is either a claim the
statute does not allow, or arithmetic that does not hold. Both are checkable
without an opinion.

Nothing here asks an LLM whether a return "looks wrong". A discrepancy is a
numeric difference against a versioned rate table, or it is not a discrepancy.
"""

from dataclasses import dataclass, field
from enum import Enum

from app.services.computation.rules.personal.deductions import DeductionInputs
from app.services.computation.rules.personal.regime_comparison_personal import (
    IncomeType,
    PersonalRegimeInput,
    RegimeRecommendation,
    compare_regimes_personal,
    compute_for_regime,
)
from app.services.computation.rules.personal.slab_tables import (
    PersonalRegime,
    get_deduction_limits,
)
from app.shared.schemas.tax_year import TaxYearContext

# Rupee difference below which declared and computed tax are treated as equal.
# Returns are filed in whole rupees and rounding differs across preparers;
# flagging a 3-rupee gap as an error would bury the real findings.
TAX_MATCH_TOLERANCE = 10.0


class DiscrepancyType(str, Enum):
    EXCESS_DEDUCTION = "excess_deduction"
    DISALLOWED_DEDUCTION = "disallowed_deduction"
    TAX_MISMATCH = "tax_mismatch"
    SUBOPTIMAL_REGIME = "suboptimal_regime"


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class FiledReturn:
    """What the taxpayer declared. Produced by itr_extractor, or supplied directly."""

    gross_income: float
    income_type: IncomeType
    regime_filed: PersonalRegime
    deductions: DeductionInputs = DeductionInputs()
    declared_tax: float | None = None
    provenance: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Discrepancy:
    type: DiscrepancyType
    severity: Severity
    section_reference: str | None
    summary: str
    declared: float | None = None
    correct: float | None = None
    cost: float | None = None
    """Rupees this discrepancy is worth: extra tax owed, or tax overpaid. Signed
    from the taxpayer's perspective -- positive means they underpaid.
    """


@dataclass(frozen=True)
class ReconciliationResult:
    discrepancies: tuple[Discrepancy, ...]
    computed_tax: float
    declared_tax: float | None
    regime_filed: PersonalRegime
    better_regime: RegimeRecommendation
    potential_saving: float
    breakeven_deductions: float | None

    @property
    def has_errors(self) -> bool:
        return bool(self.discrepancies)


_SECTION_LABELS: dict[str, str] = {
    "section_80c": "Sec 80C",
    "section_80d": "Sec 80D",
    "section_80g": "Sec 80G",
    "section_80tta": "Sec 80TTA",
    "home_loan_interest_24b": "Sec 24(b)",
    "hra_exemption": "Sec 10(13A)",
    "employer_nps_80ccd2": "Sec 80CCD(2)",
}

_CAPPED_FIELDS = {
    "section_80c": "section_80c",
    "section_80d": "section_80d_self",
    "section_80tta": "section_80tta",
    "home_loan_interest_24b": "home_loan_interest_24b",
}


def _check_deduction_claims(
    filed: FiledReturn, as_of: TaxYearContext
) -> list[Discrepancy]:
    """Claims above a statutory cap, or not available under the filed regime."""
    from app.services.computation.rules.personal.slab_tables import get_params

    params = get_params(as_of.assessment_year.ay, filed.regime_filed)
    limits = get_deduction_limits(as_of.assessment_year.ay)
    found: list[Discrepancy] = []

    for field_name, label in _SECTION_LABELS.items():
        claimed = getattr(filed.deductions, field_name, 0.0)
        if claimed <= 0:
            continue

        if field_name not in params.allowed_deductions:
            found.append(
                Discrepancy(
                    type=DiscrepancyType.DISALLOWED_DEDUCTION,
                    severity=Severity.HIGH,
                    section_reference=label,
                    summary=(
                        f"{label} was claimed but is not available under the "
                        f"{filed.regime_filed.value} regime."
                    ),
                    declared=claimed,
                    correct=0.0,
                )
            )
            continue

        cap_attr = _CAPPED_FIELDS.get(field_name)
        if cap_attr is None:
            continue

        cap = getattr(limits, cap_attr)
        if claimed > cap:
            found.append(
                Discrepancy(
                    type=DiscrepancyType.EXCESS_DEDUCTION,
                    severity=Severity.HIGH,
                    section_reference=label,
                    summary=(
                        f"{label} claimed at {claimed:,.0f} exceeds the statutory "
                        f"cap of {cap:,.0f}; the excess of {claimed - cap:,.0f} "
                        f"is not allowable."
                    ),
                    declared=claimed,
                    correct=cap,
                )
            )

    return found


def reconcile(filed: FiledReturn, as_of: TaxYearContext) -> ReconciliationResult:
    """Recompute `filed` and report every way it departs from the statute."""
    inputs = PersonalRegimeInput(
        gross_income=filed.gross_income,
        income_type=filed.income_type,
        deductions=filed.deductions,
    )

    # compute_for_regime applies caps and regime eligibility itself, so this is
    # the liability the return SHOULD have shown on its own declared figures.
    outcome = compute_for_regime(inputs, filed.regime_filed, as_of)
    comparison = compare_regimes_personal(inputs, as_of)

    discrepancies = _check_deduction_claims(filed, as_of)

    if filed.declared_tax is not None:
        gap = filed.declared_tax - outcome.total_tax
        if abs(gap) > TAX_MATCH_TOLERANCE:
            discrepancies.append(
                Discrepancy(
                    type=DiscrepancyType.TAX_MISMATCH,
                    severity=Severity.HIGH,
                    section_reference=None,
                    summary=(
                        f"Tax declared as {filed.declared_tax:,.0f} but recomputing "
                        f"from the return's own figures gives {outcome.total_tax:,.0f} "
                        f"({'under' if gap < 0 else 'over'}-stated by {abs(gap):,.0f})."
                    ),
                    declared=filed.declared_tax,
                    correct=outcome.total_tax,
                    cost=-gap,
                )
            )

    better = comparison.recommended
    filed_as = (
        RegimeRecommendation.OLD
        if filed.regime_filed is PersonalRegime.OLD
        else RegimeRecommendation.NEW
    )
    saving = 0.0

    if better is not RegimeRecommendation.EITHER and better is not filed_as:
        saving = abs(comparison.delta)
        # Not an error -- the return is lawful. It is money left on the table,
        # so it is reported as a finding but never as a high-severity defect.
        discrepancies.append(
            Discrepancy(
                type=DiscrepancyType.SUBOPTIMAL_REGIME,
                severity=Severity.MEDIUM,
                section_reference="Sec 115BAC",
                summary=(
                    f"Filed under the {filed.regime_filed.value} regime, but the "
                    f"{better.value} regime would have cost {saving:,.0f} less on "
                    f"these figures."
                ),
                declared=(
                    comparison.old_regime_tax
                    if filed.regime_filed is PersonalRegime.OLD
                    else comparison.new_regime_tax
                ),
                correct=min(comparison.old_regime_tax, comparison.new_regime_tax),
                cost=-saving,
            )
        )

    return ReconciliationResult(
        discrepancies=tuple(discrepancies),
        computed_tax=outcome.total_tax,
        declared_tax=filed.declared_tax,
        regime_filed=filed.regime_filed,
        better_regime=better,
        potential_saving=saving,
        breakeven_deductions=comparison.breakeven_deductions,
    )
