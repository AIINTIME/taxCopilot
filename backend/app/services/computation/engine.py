"""Dispatches to the correct compute_* rule function. Pure dispatcher: no I/O,
no db import, no shared.llm import. The caller (orchestration) is responsible
for fetching whatever data a rule needs and passing it in as plain values.

Each rule is registered with a RuleSpec rather than a bare callable, because
rules take differently-shaped frozen dataclasses: the spec knows how to build
that rule's input from a plain mapping and how to flatten its result back to
JSON-able outputs, so compute() stays generic.
"""

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from app.services.computation.computation_trace import (
    ComputationTrace,
    TraceStep,
    build_computation_trace,
)
from app.services.computation.rules.amt import compute_amt
from app.services.computation.rules.capital_gains import compute_capital_gains
from app.services.computation.rules.depreciation import compute_depreciation
from app.services.computation.rules.mat import compute_mat
from app.services.computation.rules.personal.deductions import DeductionInputs
from app.services.computation.rules.personal.regime_comparison_personal import (
    STATUTORY_REFERENCES as PERSONAL_REGIME_REFS,
)
from app.services.computation.rules.personal.regime_comparison_personal import (
    IncomeType,
    PersonalRegimeInput,
    PersonalRegimeResult,
    compare_regimes_personal,
)
from app.services.computation.rules.regime_comparison import compare_regimes
from app.shared.schemas.tax_year import TaxYearContext

RULES: dict[str, Callable[..., Any]] = {
    "mat": compute_mat,
    "amt": compute_amt,
    "regime_comparison": compare_regimes,
    "personal_regime_comparison": compare_regimes_personal,
    "depreciation": compute_depreciation,
    "capital_gains": compute_capital_gains,
}


class UnknownRuleError(KeyError):
    pass


@dataclass(frozen=True)
class RuleSpec:
    fn: Callable[[Any, TaxYearContext], Any]
    build_input: Callable[[Mapping[str, Any]], Any]
    to_outputs: Callable[[Any], dict[str, Any]]
    to_steps: Callable[[Any], list[TraceStep]]
    statutory_references: list[str]


def _build_personal_regime_input(inputs: Mapping[str, Any]) -> PersonalRegimeInput:
    raw_type = inputs.get("income_type", IncomeType.OTHER)
    income_type = raw_type if isinstance(raw_type, IncomeType) else IncomeType(raw_type)

    deductions = inputs.get("deductions") or {}
    if not isinstance(deductions, DeductionInputs):
        deductions = DeductionInputs(**deductions)

    return PersonalRegimeInput(
        gross_income=float(inputs["gross_income"]),
        income_type=income_type,
        deductions=deductions,
    )


def _personal_regime_outputs(result: PersonalRegimeResult) -> dict[str, Any]:
    return {
        "old_regime_tax": result.old_regime_tax,
        "new_regime_tax": result.new_regime_tax,
        "delta": result.delta,
        "recommended_regime": result.recommended.value,
        "breakeven_deductions": result.breakeven_deductions,
        "deciding_factors": list(result.deciding_factors),
        "old_taxable_income": result.old_outcome.taxable_income,
        "new_taxable_income": result.new_outcome.taxable_income,
        "disallowed_under_new": list(result.new_outcome.disallowed_deductions),
    }


_SPECS: dict[str, RuleSpec] = {
    "personal_regime_comparison": RuleSpec(
        fn=compare_regimes_personal,
        build_input=_build_personal_regime_input,
        to_outputs=_personal_regime_outputs,
        to_steps=lambda r: list(r.steps),
        statutory_references=PERSONAL_REGIME_REFS,
    ),
}


def compute(
    rule_name: str, inputs: Mapping[str, Any], as_of: TaxYearContext
) -> ComputationTrace:
    try:
        spec = _SPECS[rule_name]
    except KeyError:
        known = sorted(_SPECS)
        raise UnknownRuleError(
            f"No RuleSpec registered for {rule_name!r}. Registered: {known}. "
            f"Rules in RULES without a spec are not yet callable through the engine."
        ) from None

    rule_input = spec.build_input(inputs)
    result = spec.fn(rule_input, as_of)

    return build_computation_trace(
        rule_name=rule_name,
        inputs=dict(inputs),
        outputs=spec.to_outputs(result),
        statutory_references=list(spec.statutory_references),
        as_of=as_of,
        steps=spec.to_steps(result),
    )
