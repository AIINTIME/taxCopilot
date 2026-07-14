"""Citation schema. Every claim the LLM makes must be tagged with one of these,
and every citation must be verified against retrieved chunks by
services/rag/evidence_gate.py before being shown to the user (Evidence Gate).
"""

from pydantic import BaseModel, Field


class Citation(BaseModel):
    chunk_id: str
    source_id: str
    section_reference: str | None = None
    excerpt: str
    confidence: float = Field(ge=0.0, le=1.0)
    verified: bool = False
