"""Alternate Minimum Tax -- Sec 115JC of the Income-tax Act 1961 (and its
2025-Act equivalent). Pure function, zero I/O.

Rate: 18.5% of adjusted total income plus Health & Education Cess of 4%,
giving an effective rate of 19.24%. Surcharge is not added here for the same
reason as compute_mat -- AMTInput does not carry the income tier surcharge
depends on. The 2025-Act rate is assumed unchanged, PENDING DOMAIN-EXPERT
VERIFICATION once that Act is in force.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.shared.schemas.tax_year import TaxYearContext

AMT_BASE_RATE = Decimal("0.185")
HEALTH_EDUCATION_CESS_RATE = Decimal("0.04")
AMT_EFFECTIVE_RATE = AMT_BASE_RATE * (1 + HEALTH_EDUCATION_CESS_RATE)  # 0.1924


@dataclass(frozen=True)
class AMTInput:
    adjusted_total_income: Decimal
    normal_tax_payable: Decimal


@dataclass(frozen=True)
class AMTResult:
    amt_liability: Decimal
    amt_rate_applied: Decimal
    tax_payable: Decimal


def compute_amt(inputs: AMTInput, as_of: TaxYearContext) -> AMTResult:
    if inputs.adjusted_total_income < 0:
        raise ValueError("adjusted_total_income cannot be negative")
    if inputs.normal_tax_payable < 0:
        raise ValueError("normal_tax_payable cannot be negative")

    rate = AMT_EFFECTIVE_RATE
    amt_liability = (inputs.adjusted_total_income * rate).quantize(Decimal("0.01"))
    tax_payable = max(amt_liability, inputs.normal_tax_payable)

    return AMTResult(amt_liability=amt_liability, amt_rate_applied=rate, tax_payable=tax_payable)
