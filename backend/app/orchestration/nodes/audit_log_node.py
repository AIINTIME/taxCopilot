"""Writes the final, insert-only AuditLog row. Never updates or deletes an
existing row -- every query produces exactly one new row.

Runs for EVERY terminal path, including clarifications and failed retrievals:
the audit trail records what the system was asked and what it answered, and a
trail with gaps is not a trail. That is also why a write failure here must not
sink an otherwise good answer -- the user gets their response and the failure
is logged loudly.
"""

import logging
from datetime import datetime, time, timezone

from prisma import Json

from app.db import prisma
from app.orchestration.state import QueryGraphState

logger = logging.getLogger(__name__)


async def write_audit_log(state: QueryGraphState) -> dict:
    response = state.get("final_response") or {}
    llm_response = state.get("llm_response") or {}
    citations = state.get("gated_citations") or []

    try:
        row = await prisma.auditlog.create(
            data={
                "userId": state.get("user_id"),
                "query": state["query"],
                "retrievedChunkIds": [
                    chunk["chunk_id"]
                    for chunk in state.get("retrieved_chunks") or []
                    if chunk.get("chunk_id")
                ],
                # A pure computation involves no model. Recording the provider
                # as "computation" rather than blank keeps every row honest
                # about what produced the answer.
                "modelVersion": llm_response.get("model_version") or "n/a",
                "providerName": llm_response.get("provider_name") or "computation",
                "response": response.get("answer") or "",
                # Prisma's Json column needs the explicit wrapper; a bare list
                # is rejected as an untyped input.
                "citations": Json([c.model_dump(mode="json") for c in citations]),
                "gateStatus": state.get("gate_status") or "VERIFIED",
                # AuditLog.asOfDate is a Prisma DateTime, but TaxYearContext
                # carries a plain date. Prisma rejects both a date and an ISO
                # string here (surfacing, unhelpfully, as FieldNotFoundError on
                # the field rather than a type error), so widen to an explicit
                # UTC datetime at midnight.
                "asOfDate": datetime.combine(
                    state["as_of"].as_of_date, time.min, tzinfo=timezone.utc
                ),
            }
        )
    except Exception as exc:
        logger.exception("audit log write failed for query %r: %s", state["query"], exc)
        return {"audit_entry": {"id": None, "persisted": False}}

    return {"audit_entry": {"id": row.id, "persisted": True}}
