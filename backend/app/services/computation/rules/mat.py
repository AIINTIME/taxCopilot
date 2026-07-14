"""Minimum Alternate Tax -- Sec 115JB of the Income-tax Act 1961 (and its
2025-Act equivalent). Pure function, zero I/O.
"""

from dataclasses import dataclass

from app.shared.schemas.tax_year import TaxYearContext


@dataclass(frozen=True)
class MATInput:
    book_profit: float
    normal_tax_payable: float


@dataclass(frozen=True)
class MATResult:
    mat_liability: float
    mat_rate_applied: float
    tax_payable: float


def compute_mat(inputs: MATInput, as_of: TaxYearContext) -> MATResult:
    raise NotImplementedError("TODO: implement Sec 115JB MAT computation")
