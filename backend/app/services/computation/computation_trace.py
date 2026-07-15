"""Builds the audit-tagged trace object for a single rule invocation: which
rule ran, what inputs/outputs it had, which statutory references apply, and
the as-of context it ran under. Consumed by orchestration/nodes/
assemble_response.py and orchestration/nodes/audit_log_node.py.

Every TraceStep carries the statutory reference it derives from. This is what
orchestration/nodes/computation_citations.py resolves against the Neo4j rule
graph, so a computation-only answer still returns real citations -- a step
without a section_reference cannot be cited.
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.shared.schemas.tax_year import TaxYearContext


class TraceStep(BaseModel):
    """One line of a shown computation, e.g. "Slab 4-8L @ 5% -> 20,000"."""

    label: str
    amount: float
    section_reference: str | None = None
    detail: str | None = None


class ComputationTrace(BaseModel):
    rule_name: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    steps: list[TraceStep] = Field(default_factory=list)
    statutory_references: list[str]
    as_of: TaxYearContext
    computed_at: datetime


def build_computation_trace(
    rule_name: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    statutory_references: list[str],
    as_of: TaxYearContext,
    steps: list[TraceStep] | None = None,
) -> ComputationTrace:
    steps = steps or []

    merged = list(statutory_references)
    for step in steps:
        if step.section_reference and step.section_reference not in merged:
            merged.append(step.section_reference)

    return ComputationTrace(
        rule_name=rule_name,
        inputs=inputs,
        outputs=outputs,
        steps=steps,
        statutory_references=merged,
        as_of=as_of,
        computed_at=datetime.now(timezone.utc),
    )
