"""Dispatches to the correct compute_* rule function. Pure dispatcher: no I/O,
no db import, no shared.llm import. The caller (orchestration) is responsible
for fetching whatever data a rule needs and passing it in as plain values.
"""

import dataclasses
import types
from datetime import date
from typing import Any, Callable, Mapping

from app.services.computation.computation_trace import ComputationTrace, build_computation_trace
from app.services.computation.rules.amt import AMTInput, compute_amt
from app.services.computation.rules.capital_gains import CapitalGainsInput, compute_capital_gains
from app.services.computation.rules.capital_gains_exemptions import (
    ExemptionInput,
    compute_exemption,
)
from app.services.computation.rules.depreciation import DepreciationInput, compute_depreciation
from app.services.computation.rules.mat import MATInput, compute_mat
from app.services.computation.rules.regime_comparison import (
    RegimeComparisonInput,
    compare_regimes,
)
from app.services.computation.validators import validate_no_estimates
from app.shared.schemas.tax_year import TaxActRegime, TaxYearContext

RULES: dict[str, Callable[..., Any]] = {
    "mat": compute_mat,
    "amt": compute_amt,
    "regime_comparison": compare_regimes,
    "depreciation": compute_depreciation,
    "capital_gains": compute_capital_gains,
    "capital_gains_exemption": compute_exemption,
}

RULE_INPUT_TYPES: dict[str, type] = {
    "mat": MATInput,
    "amt": AMTInput,
    "regime_comparison": RegimeComparisonInput,
    "depreciation": DepreciationInput,
    "capital_gains": CapitalGainsInput,
    "capital_gains_exemption": ExemptionInput,
}

# 1961-Act citations are confirmed; the 2025-Act equivalents' exact section
# numbers are not yet confirmed from the ingested corpus (see plan) -- cited
# generically pending Phase 2/3 ingestion of the rate-provision text.
_STATUTORY_REFERENCES_1961: dict[str, list[str]] = {
    "mat": ["Income-tax Act 1961, Sec 115JB"],
    "amt": ["Income-tax Act 1961, Sec 115JC"],
    "regime_comparison": ["Income-tax Act 1961, Sec 115BAA", "Income-tax Act 1961, Sec 115BAB"],
    "depreciation": ["Income-tax Act 1961, Sec 32", "Schedule III, Companies Act 2013"],
    "capital_gains": [
        "Income-tax Act 1961, Sec 45",
        "Income-tax Act 1961, Sec 48",
        "Income-tax Act 1961, Sec 111A",
        "Income-tax Act 1961, Sec 112",
        "Income-tax Act 1961, Sec 112A",
    ],
    "capital_gains_exemption": [
        "Income-tax Act 1961, Sec 54",
        "Income-tax Act 1961, Sec 54B",
        "Income-tax Act 1961, Sec 54EC",
        "Income-tax Act 1961, Sec 54F",
    ],
}


def _statutory_references(rule_name: str, as_of: TaxYearContext) -> list[str]:
    references_1961 = _STATUTORY_REFERENCES_1961.get(rule_name, [])
    if as_of.regime == TaxActRegime.ACT_1961:
        return references_1961
    return [
        f"Income-tax Act 2025 equivalent of: {ref} (exact section number "
        "pending ingestion verification)"
        for ref in references_1961
    ]


def _coerce_value(value: Any, field_type: Any) -> Any:
    """Coerce JSON-shaped values (e.g. an ISO date string from an HTTP
    caller) into what the rule's dataclass field actually expects. Every
    computation_request.inputs value arrives from routes.py as whatever JSON
    produces (str/int/float/bool/None) -- dataclasses do no such coercion
    themselves, so without this a real HTTP caller's ISO date strings would
    reach a rule function as `str` instead of `date` and break on the first
    date comparison.
    """
    if isinstance(field_type, types.UnionType):
        non_none = [t for t in field_type.__args__ if t is not type(None)]
        field_type = non_none[0] if len(non_none) == 1 else None

    if field_type is date and isinstance(value, str):
        return date.fromisoformat(value)
    return value


def _build_rule_input(rule_name: str, inputs: Mapping[str, Any]) -> Any:
    input_type = RULE_INPUT_TYPES.get(rule_name)
    if input_type is None:
        raise ValueError(f"Unknown rule_name: {rule_name!r}")
    fields_by_name = {f.name: f for f in dataclasses.fields(input_type)}
    unknown_keys = set(inputs) - set(fields_by_name)
    if unknown_keys:
        raise ValueError(
            f"Unknown input field(s) for rule {rule_name!r}: {sorted(unknown_keys)}"
        )
    coerced_inputs = {
        name: _coerce_value(value, fields_by_name[name].type) for name, value in inputs.items()
    }
    return input_type(**coerced_inputs)


def compute(
    rule_name: str, inputs: Mapping[str, Any], as_of: TaxYearContext
) -> ComputationTrace:
    if rule_name not in RULES:
        raise ValueError(f"Unknown rule_name: {rule_name!r}")

    validate_no_estimates(inputs)
    rule_input = _build_rule_input(rule_name, inputs)
    result = RULES[rule_name](rule_input, as_of)

    return build_computation_trace(
        rule_name=rule_name,
        inputs=dict(inputs),
        outputs=dataclasses.asdict(result),
        statutory_references=_statutory_references(rule_name, as_of),
        as_of=as_of,
    )
