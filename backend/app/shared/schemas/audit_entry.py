"""In-memory representation of an audit row, mirroring the `AuditLog` Prisma
model 1:1. orchestration/nodes/audit_log_node.py builds one of these and
persists it as an insert-only row -- never updated or deleted.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.shared.schemas.citation import Citation

GateStatusLiteral = Literal["VERIFIED", "FLAGGED", "PARTIAL"]


class AuditEntry(BaseModel):
    user_id: str | None = None
    query: str
    retrieved_chunk_ids: list[str] = []
    model_version: str
    provider_name: str
    response: str
    citations: list[Citation] = []
    gate_status: GateStatusLiteral
    as_of_date: date
    created_at: datetime | None = None
