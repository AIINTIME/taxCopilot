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
from app.services.computation.rules.depreciation import DepreciationInput, compute_depreciation
from app.services.computation.rules.mat import MATInput, compute_mat
from app.services.computation.rules.regime_comparison import (
    RegimeComparisonInput,
    compare_regimes,
)
from app.shared.schemas.tax_year import TaxYearContext

RULES: dict[str, Callable[..., Any]] = {
    "mat": compute_mat,
    "amt": compute_amt,
    "regime_comparison": compare_regimes,
    "depreciation": compute_depreciation,
    "capital_gains": compute_capital_gains,
}

_INPUT_TYPES: dict[str, type] = {
    "mat": MATInput,
    "amt": AMTInput,
    "regime_comparison": RegimeComparisonInput,
    "depreciation": DepreciationInput,
    "capital_gains": CapitalGainsInput,
}

_STATUTORY_REFERENCES: dict[str, list[str]] = {
    "mat": ["Section 115JB, Income-tax Act 1961"],
    "amt": ["Section 115JC, Income-tax Act 1961"],
    "regime_comparison": [
        "Section 115BAA, Income-tax Act 1961",
        "Section 115BAB, Income-tax Act 1961",
    ],
    "depreciation": ["Schedule III, Companies Act 2013", "Income-tax Act 1961 (WDV method)"],
    "capital_gains": ["Finance (No. 2) Act, 2024 -- capital gains rate/indexation change"],
}


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
    missing: list[str] = []
    kwargs: dict[str, Any] = {}

    for f in fields(dataclass_type):
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

    dataclass_type = _INPUT_TYPES[rule_name]
    rule_fn = RULES[rule_name]

    rule_input = _build_input(rule_name, dataclass_type, inputs)
    result = rule_fn(rule_input, as_of)

    return build_computation_trace(
        rule_name=rule_name,
        inputs={f.name: getattr(rule_input, f.name) for f in fields(dataclass_type)},
        outputs={f.name: getattr(result, f.name) for f in fields(result)},
        statutory_references=_STATUTORY_REFERENCES[rule_name],
        as_of=as_of,
    )
