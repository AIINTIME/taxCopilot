"""Dispatches to the correct compute_* rule function. Pure dispatcher: no I/O,
no db import, no shared.llm import. The caller (orchestration) is responsible
for fetching whatever data a rule needs and passing it in as plain values.
"""

from typing import Any, Callable, Mapping

from app.services.computation.computation_trace import ComputationTrace
from app.services.computation.rules.amt import compute_amt
from app.services.computation.rules.capital_gains import compute_capital_gains
from app.services.computation.rules.depreciation import compute_depreciation
from app.services.computation.rules.mat import compute_mat
from app.services.computation.rules.regime_comparison import compare_regimes
from app.shared.schemas.tax_year import TaxYearContext

RULES: dict[str, Callable[..., Any]] = {
    "mat": compute_mat,
    "amt": compute_amt,
    "regime_comparison": compare_regimes,
    "depreciation": compute_depreciation,
    "capital_gains": compute_capital_gains,
}


def compute(
    rule_name: str, inputs: Mapping[str, Any], as_of: TaxYearContext
) -> ComputationTrace:
    raise NotImplementedError(
        "TODO: look up RULES[rule_name], build its dataclass input from "
        "`inputs`, call it, and wrap the result in a ComputationTrace"
    )
