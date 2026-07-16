"""Dispatches to the correct compute_* rule function. Pure dispatcher: no I/O,
no db import, no shared.llm import. The caller (orchestration) is responsible
for fetching whatever data a rule needs and passing it in as plain values.
"""

from dataclasses import MISSING, fields
from datetime import date as date_type
from decimal import Decimal, InvalidOperation
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

_INPUT_TYPES: dict[str, type] = {
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
        "Finance (No. 2) Act, 2024 -- capital gains rate/indexation change",
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


class MissingComputationInputError(ValueError):
    def __init__(self, rule_name: str, missing_fields: list[str]) -> None:
        self.rule_name = rule_name
        self.missing_fields = missing_fields
        super().__init__(
            f"Missing required input(s) for '{rule_name}': {', '.join(missing_fields)}"
        )


def _coerce_value(field_name: str, field_type: Any, raw_value: Any) -> Any:
    try:
        if field_type is Decimal and not isinstance(raw_value, Decimal):
            return Decimal(str(raw_value))
        if field_type is date_type and isinstance(raw_value, str):
            return date_type.fromisoformat(raw_value)
        return raw_value
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid value for '{field_name}': {raw_value!r} ({exc})") from exc


def _build_input(rule_name: str, dataclass_type: type, inputs: Mapping[str, Any]) -> Any:
    fields_by_name = {f.name: f for f in fields(dataclass_type)}
    unknown_keys = set(inputs) - set(fields_by_name)
    if unknown_keys:
        raise ValueError(
            f"Unknown input field(s) for rule {rule_name!r}: {sorted(unknown_keys)}"
        )

    missing: list[str] = []
    kwargs: dict[str, Any] = {}

    for f in fields_by_name.values():
        if f.name in inputs and inputs[f.name] is not None:
            kwargs[f.name] = _coerce_value(f.name, f.type, inputs[f.name])
        elif f.default is MISSING and f.default_factory is MISSING:  # type: ignore[misc]
            missing.append(f.name)

    if missing:
        raise MissingComputationInputError(rule_name, missing)

    return dataclass_type(**kwargs)


def compute(
    rule_name: str, inputs: Mapping[str, Any], as_of: TaxYearContext
) -> ComputationTrace:
    if rule_name not in RULES:
        raise ValueError(f"Unknown computation rule: {rule_name!r}. Known rules: {sorted(RULES)}")

    validate_no_estimates(inputs)

    dataclass_type = _INPUT_TYPES[rule_name]
    rule_fn = RULES[rule_name]

    rule_input = _build_input(rule_name, dataclass_type, inputs)
    result = rule_fn(rule_input, as_of)

    return build_computation_trace(
        rule_name=rule_name,
        inputs={f.name: getattr(rule_input, f.name) for f in fields(dataclass_type)},
        outputs={f.name: getattr(result, f.name) for f in fields(result)},
        statutory_references=_statutory_references(rule_name, as_of),
        as_of=as_of,
    )
