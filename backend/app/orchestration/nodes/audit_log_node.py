"""Writes the final, insert-only AuditLog row. Never updates or deletes an
existing row -- every query produces exactly one new row.

Runs for EVERY terminal path, including clarifications and failed retrievals:
the audit trail records what the system was asked and what it answered, and a
trail with gaps is not a trail. That is also why a write failure here must not
sink an otherwise good answer -- the user gets their response and the failure
is logged loudly instead.
"""

import logging
from datetime import datetime, timezone

from prisma import Json

from app.db import prisma
from app.orchestration.state import QueryGraphState

logger = logging.getLogger(__name__)


async def write_audit_log(state: QueryGraphState) -> dict:
    final_response = state["final_response"]
    llm_response = state.get("llm_response") or {}
    retrieved_chunks = state.get("retrieved_chunks") or []
    as_of_date = final_response["as_of_date"]
    as_of_datetime = datetime.combine(as_of_date, datetime.min.time(), tzinfo=timezone.utc)

    citations = final_response.get("citations", [])
    citations_json = [
        c.model_dump(mode="json") if hasattr(c, "model_dump") else c for c in citations
    ]
    retrieved_chunk_ids = [
        chunk["chunk_id"] for chunk in retrieved_chunks if chunk.get("chunk_id")
    ]

    try:
        logger.info("[FLOW] audit_log: hitting Postgres (prisma.auditlog.create)")
        audit_log = await prisma.auditlog.create(
            data={
                "userId": state.get("user_id"),
                "query": state["query"],
                "retrievedChunkIds": retrieved_chunk_ids,
                "modelVersion": llm_response.get("model_version", "deterministic-computation-engine"),
                "providerName": llm_response.get("provider_name", "internal"),
                "response": final_response.get("answer", ""),
                "citations": Json(citations_json),
                "gateStatus": final_response.get("gate_status", "FLAGGED"),
                "asOfDate": as_of_datetime,
            }
        )
    except Exception:
        logger.exception("[FLOW] audit_log: Postgres write FAILED for query=%r", state["query"])
        # A failed audit write must not take down an otherwise-good answer --
        # the user still gets their response; the gap is logged loudly above
        # instead. audit_log_id is set to "" (rather than left absent) since
        # QueryResponse.audit_log_id is a required str field.
        return {
            "audit_entry": {"id": None, "persisted": False},
            "final_response": {**final_response, "audit_log_id": ""},
        }

    logger.info("[FLOW] audit_log: Postgres write confirmed, id=%s", audit_log.id)

    audit_entry = {
        "id": audit_log.id,
        "persisted": True,
        "user_id": state.get("user_id"),
        "query": state["query"],
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "model_version": llm_response.get("model_version", "deterministic-computation-engine"),
        "provider_name": llm_response.get("provider_name", "internal"),
        "response": final_response.get("answer", ""),
        "citations": citations_json,
        "gate_status": final_response.get("gate_status", "FLAGGED"),
        "as_of_date": as_of_date,
        "created_at": audit_log.createdAt,
    }

    return {
        "audit_entry": audit_entry,
        "final_response": {**final_response, "audit_log_id": audit_log.id},
    }
