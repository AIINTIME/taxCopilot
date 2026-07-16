"""Builds the audit-tagged trace object for a single rule invocation: which
rule ran, what inputs/outputs it had, which statutory references apply, and
the as-of context it ran under. Consumed by orchestration/nodes/
assemble_response.py and orchestration/nodes/audit_log_node.py.
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from app.shared.schemas.tax_year import TaxYearContext


class ComputationTrace(BaseModel):
    rule_name: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    statutory_references: list[str]
    as_of: TaxYearContext
    computed_at: datetime


def build_computation_trace(
    rule_name: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    statutory_references: list[str],
    as_of: TaxYearContext,
) -> ComputationTrace:
    return ComputationTrace(
        rule_name=rule_name,
        inputs=inputs,
        outputs=outputs,
        statutory_references=statutory_references,
        as_of=as_of,
        computed_at=datetime.now(timezone.utc),
    )
