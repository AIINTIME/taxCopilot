"""Alternate Minimum Tax -- Sec 115JC of the Income-tax Act 1961 (and its
2025-Act equivalent). Pure function, zero I/O.
"""

from dataclasses import dataclass

from app.shared.schemas.tax_year import TaxYearContext


@dataclass(frozen=True)
class AMTInput:
    adjusted_total_income: float
    normal_tax_payable: float


@dataclass(frozen=True)
class AMTResult:
    amt_liability: float
    amt_rate_applied: float
    tax_payable: float


def compute_amt(inputs: AMTInput, as_of: TaxYearContext) -> AMTResult:
    raise NotImplementedError("TODO: implement Sec 115JC AMT computation")
