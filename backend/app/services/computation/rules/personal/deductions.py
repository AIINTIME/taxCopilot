"""Chapter VI-A and salary deductions for individuals. Pure, zero I/O.

Caps and regime-eligibility both come from slab_tables -- this module holds
the mechanics (apply cap, honour eligibility, emit a trace step) and no
statutory figures of its own.

Deductions denied by the elected regime are reported in `disallowed` rather
than silently zeroed: an old-vs-new comparison has to be able to say WHICH
deductions the new regime costs the taxpayer, which is what drives
`deciding_factors` in regime_comparison_personal.py.
"""

from dataclasses import dataclass, fields

from app.services.computation.computation_trace import TraceStep
from app.services.computation.rules.personal.slab_tables import (
    DeductionLimits,
    RegimeParams,
)

_SECTION_LABELS: dict[str, str] = {
    "section_80c": "Sec 80C",
    "section_80d": "Sec 80D",
    "section_80g": "Sec 80G",
    "section_80tta": "Sec 80TTA",
    "home_loan_interest_24b": "Sec 24(b)",
    "hra_exemption": "Sec 10(13A)",
    "employer_nps_80ccd2": "Sec 80CCD(2)",
}


@dataclass(frozen=True)
class DeductionInputs:
    """Amounts the taxpayer claims, before caps. Field names are the keys used
    by RegimeParams.allowed_deductions and _SECTION_LABELS.
    """

    section_80c: float = 0.0
    section_80d: float = 0.0
    section_80g: float = 0.0
    section_80tta: float = 0.0
    home_loan_interest_24b: float = 0.0
    hra_exemption: float = 0.0
    employer_nps_80ccd2: float = 0.0

    def total_claimed(self) -> float:
        return sum(getattr(self, f.name) for f in fields(self))


@dataclass(frozen=True)
class DeductionResult:
    total: float
    steps: tuple[TraceStep, ...]
    disallowed: tuple[str, ...]
    capped: tuple[str, ...]


def _cap_for(field_name: str, limits: DeductionLimits) -> float | None:
    if field_name == "section_80c":
        return limits.section_80c
    if field_name == "section_80d":
        return limits.section_80d_self
    if field_name == "section_80tta":
        return limits.section_80tta
    if field_name == "home_loan_interest_24b":
        return limits.home_loan_interest_24b
    return None


def compute_deductions(
    inputs: DeductionInputs, params: RegimeParams, limits: DeductionLimits
) -> DeductionResult:
    total = 0.0
    steps: list[TraceStep] = []
    disallowed: list[str] = []
    capped: list[str] = []

    for field in fields(inputs):
        name = field.name
        claimed = getattr(inputs, name)
        if claimed <= 0:
            continue

        label = _SECTION_LABELS[name]

        if name not in params.allowed_deductions:
            disallowed.append(label)
            continue

        cap = _cap_for(name, limits)
        allowed = min(claimed, cap) if cap is not None else claimed
        if cap is not None and claimed > cap:
            capped.append(label)

        total += allowed
        steps.append(
            TraceStep(
                label=f"Deduction {label}",
                amount=-allowed,
                section_reference=label,
                detail=(
                    f"claimed {claimed:,.0f}, capped at {cap:,.0f}"
                    if cap is not None and claimed > cap
                    else f"claimed {claimed:,.0f}"
                ),
            )
        )

    return DeductionResult(
        total=total,
        steps=tuple(steps),
        disallowed=tuple(disallowed),
        capped=tuple(capped),
    )
