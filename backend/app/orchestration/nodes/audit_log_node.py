"""Writes the final, insert-only AuditLog row. Never updates or deletes an
existing row -- every query produces exactly one new row.
"""

from app.db import prisma
from app.orchestration.state import QueryGraphState


async def write_audit_log(state: QueryGraphState) -> dict:
    raise NotImplementedError(
        "TODO: build the AuditLog.create(data={...}) payload from "
        "state['query'], state['retrieved_chunks'], state['llm_response'], "
        "state['gated_citations'], state['gate_status'], state['as_of'], and "
        "state['user_id'], via prisma.auditlog.create(...), then set "
        "state['audit_entry'] to the persisted row"
    )
