"""Writes the final, insert-only AuditLog row. Never updates or deletes an
existing row -- every query produces exactly one new row.
"""

import logging
from datetime import datetime

from prisma import Json

from app.db import prisma
from app.orchestration.state import QueryGraphState

logger = logging.getLogger(__name__)


async def write_audit_log(state: QueryGraphState) -> dict:
    final_response = state["final_response"]
    llm_response = state.get("llm_response") or {}
    retrieved_chunks = state.get("retrieved_chunks", [])
    as_of_date = final_response["as_of_date"]

    logger.info("[FLOW] audit_log: hitting Postgres (prisma.auditlog.create)")
    audit_log = await prisma.auditlog.create(
        data={
            "userId": state.get("user_id"),
            "query": state["query"],
            "retrievedChunkIds": [chunk["chunk_id"] for chunk in retrieved_chunks],
            "modelVersion": llm_response.get("model_version", ""),
            "providerName": llm_response.get("provider_name", ""),
            "response": final_response["answer"],
            "citations": Json(final_response["citations"]),
            "gateStatus": final_response["gate_status"],
            "asOfDate": datetime.combine(as_of_date, datetime.min.time()),
        }
    )
    logger.info("[FLOW] audit_log: Postgres write confirmed, id=%s", audit_log.id)

    audit_entry = {
        "id": audit_log.id,
        "user_id": state.get("user_id"),
        "query": state["query"],
        "retrieved_chunk_ids": [chunk["chunk_id"] for chunk in retrieved_chunks],
        "model_version": llm_response.get("model_version", ""),
        "provider_name": llm_response.get("provider_name", ""),
        "response": final_response["answer"],
        "citations": final_response["citations"],
        "gate_status": final_response["gate_status"],
        "as_of_date": as_of_date,
        "created_at": audit_log.createdAt,
    }

    return {
        "audit_entry": audit_entry,
        "final_response": {**final_response, "audit_log_id": audit_log.id},
    }
