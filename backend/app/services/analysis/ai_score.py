"""The AI score shown against an uploaded return. Pure, deterministic.

Two sub-scores, because they answer different questions and averaging them
into one number would hide both:

    accuracy -- is the arithmetic right? Does the declared tax match what the
                return's own figures produce under the statute?
    risk     -- what does it expose the filer to? Driven by the severity of
                what was found and the rupees at stake.

A return can be perfectly accurate and still carry risk (a lawful but costly
regime choice), or be inaccurate in the taxpayer's favour and carry a lot
(an over-claimed deduction). One number cannot say both.

NEVER ASKED OF AN LLM. The score is a function of reconciler output, which is
itself a function of versioned rate tables. Asking a model to "rate this
return" would make the number unreproducible, unexplainable, and unauditable --
and this number is the one users will screenshot.
"""

from dataclasses import dataclass
from enum import Enum

from app.services.analysis.reconciler import (
    DiscrepancyType,
    ReconciliationResult,
    Severity,
)

_SEVERITY_WEIGHT: dict[Severity, float] = {
    Severity.HIGH: 1.0,
    Severity.MEDIUM: 0.5,
    Severity.LOW: 0.2,
}

# Rupees of exposure at which risk from money at stake is considered maxed out.
# Above this the severity mix, not the amount, is what differentiates returns.
_EXPOSURE_CEILING = 500_000.0

# A lawful-but-costly regime choice is not a compliance risk: nothing is owed
# and nothing is penalised. It must not drag the risk score the way an
# over-claim does.
_NON_COMPLIANCE_TYPES = frozenset({DiscrepancyType.SUBOPTIMAL_REGIME})


class Grade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


@dataclass(frozen=True)
class AIScore:
    accuracy: float
    """0-100. How closely the declared tax matches the recomputed liability."""

    risk: float
    """0-100, HIGHER IS WORSE. Severity and rupees of compliance exposure."""

    grade: Grade
    overall: float
    """0-100, higher is better. Combines accuracy with the inverse of risk."""

    findings: int
    exposure: float
    """Rupees of tax underpaid across all findings. 0 when nothing is owed."""

    explanation: tuple[str, ...]


def _accuracy(result: ReconciliationResult) -> float:
    if result.declared_tax is None:
        # Nothing was declared to check against. Neither credit nor blame:
        # withhold judgement rather than invent a perfect score.
        return 100.0 if not result.discrepancies else 50.0

    if result.computed_tax <= 0:
        return 100.0 if abs(result.declared_tax) <= 10 else 0.0

    error = abs(result.declared_tax - result.computed_tax) / result.computed_tax
    return round(max(0.0, 100.0 * (1.0 - min(error, 1.0))), 1)


def _risk(result: ReconciliationResult) -> tuple[float, float]:
    compliance = [
        d
        for d in result.discrepancies
        if d.type not in _NON_COMPLIANCE_TYPES
        # A finding with a known, non-positive cost is one where the filer paid
        # too MUCH. That is an accuracy problem, not an exposure: nobody is
        # penalised for overpaying, and letting it drive risk would tell a
        # taxpayer who over-remitted that they are at risk from the department.
        # Findings with no cost computed (an over-claimed deduction on a return
        # that stated no tax) stay in -- unknown is not the same as harmless.
        and not (d.cost is not None and d.cost <= 0)
    ]
    if not compliance:
        return 0.0, 0.0

    # Only underpayment is exposure.
    exposure = sum(d.cost for d in compliance if d.cost and d.cost > 0)

    severity = max(_SEVERITY_WEIGHT[d.severity] for d in compliance)
    volume = min(len(compliance) / 5.0, 1.0)
    money = min(exposure / _EXPOSURE_CEILING, 1.0) if exposure else 0.0

    risk = 100.0 * min(1.0, 0.5 * severity + 0.2 * volume + 0.3 * money)
    return round(risk, 1), exposure


def _grade(overall: float) -> Grade:
    if overall >= 90:
        return Grade.A
    if overall >= 75:
        return Grade.B
    if overall >= 50:
        return Grade.C
    return Grade.D


def score_return(result: ReconciliationResult) -> AIScore:
    accuracy = _accuracy(result)
    risk, exposure = _risk(result)

    overall = round(0.6 * accuracy + 0.4 * (100.0 - risk), 1)

    explanation: list[str] = []
    if not result.discrepancies:
        explanation.append("No discrepancies found against the return's own figures.")
    for d in result.discrepancies:
        explanation.append(f"[{d.severity.value.upper()}] {d.summary}")
    if exposure > 0:
        explanation.append(f"Estimated additional tax at stake: {exposure:,.0f}.")

    return AIScore(
        accuracy=accuracy,
        risk=risk,
        grade=_grade(overall),
        overall=overall,
        findings=len(result.discrepancies),
        exposure=exposure,
        explanation=tuple(explanation),
    )
