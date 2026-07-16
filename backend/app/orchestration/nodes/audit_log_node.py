"""Writes the final, insert-only AuditLog row. Never updates or deletes an
existing row -- every query produces exactly one new row.
"""

from datetime import datetime, timezone

from prisma import Json

from app.db import prisma
from app.orchestration.state import QueryGraphState


async def write_audit_log(state: QueryGraphState) -> dict:
    final_response = state["final_response"]
    llm_response = state.get("llm_response")
    retrieved_chunk_ids = [c["chunk_id"] for c in state.get("retrieved_chunks", [])]

    citations = final_response.get("citations", [])
    citations_json = [
        c.model_dump(mode="json") if hasattr(c, "model_dump") else c for c in citations
    ]

    as_of_date = state["as_of"].as_of_date
    as_of_datetime = datetime.combine(as_of_date, datetime.min.time(), tzinfo=timezone.utc)

    row = await prisma.auditlog.create(
        data={
            "userId": state.get("user_id"),
            "query": state["query"],
            "retrievedChunkIds": retrieved_chunk_ids,
            "modelVersion": llm_response["model_version"] if llm_response else "deterministic-computation-engine",
            "providerName": llm_response["provider_name"] if llm_response else "internal",
            "response": final_response.get("answer", ""),
            "citations": Json(citations_json),
            "gateStatus": final_response.get("gate_status", "FLAGGED"),
            "asOfDate": as_of_datetime,
        }
    )

    return {"audit_entry": {"id": row.id}}
