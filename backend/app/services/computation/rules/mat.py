"""Minimum Alternate Tax -- Sec 115JB of the Income-tax Act 1961 (and its
2025-Act equivalent). Pure function, zero I/O.

Rate note: MAT is 15% of book profit (post Finance Act 2019, AY 2020-21
onwards) plus Health & Education Cess of 4% on that amount, giving an
effective rate of 15.6%. This function does NOT add surcharge, because
MATInput does not carry the total-income tier surcharge depends on --
callers needing an exact final payable figure must add surcharge separately
once that input is available; this is a deliberate scope boundary, not a
silent omission. The 2025-Act rate is assumed unchanged from the 1961-Act
rate (the Income-tax Act 2025 was a restructuring/renumbering exercise per
public record, not a stated rate change) but this specific point is
flagged as PENDING DOMAIN-EXPERT VERIFICATION once the 2025 Act is in force.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.shared.schemas.tax_year import TaxActRegime, TaxYearContext

MAT_BASE_RATE = Decimal("0.15")
HEALTH_EDUCATION_CESS_RATE = Decimal("0.04")
MAT_EFFECTIVE_RATE = MAT_BASE_RATE * (1 + HEALTH_EDUCATION_CESS_RATE)  # 0.156


@dataclass(frozen=True)
class MATInput:
    book_profit: Decimal
    normal_tax_payable: Decimal


@dataclass(frozen=True)
class MATResult:
    mat_liability: Decimal
    mat_rate_applied: Decimal
    tax_payable: Decimal


def compute_mat(inputs: MATInput, as_of: TaxYearContext) -> MATResult:
    if inputs.book_profit < 0:
        raise ValueError("book_profit cannot be negative")
    if inputs.normal_tax_payable < 0:
        raise ValueError("normal_tax_payable cannot be negative")

    # Rate is the same figure under both regimes per the module docstring's
    # caveat -- as_of.regime is threaded through so a future amendment only
    # needs to branch here, not change every call site.
    rate = MAT_EFFECTIVE_RATE
    if as_of.regime == TaxActRegime.ACT_2025:
        rate = MAT_EFFECTIVE_RATE  # pending domain-expert verification

    mat_liability = (inputs.book_profit * rate).quantize(Decimal("0.01"))
    tax_payable = max(mat_liability, inputs.normal_tax_payable)

    return MATResult(
        mat_liability=mat_liability,
        mat_rate_applied=rate,
        tax_payable=tax_payable,
    )
