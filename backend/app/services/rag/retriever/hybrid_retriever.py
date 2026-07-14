"""Reciprocal Rank Fusion of vector_store + keyword_store results, filtered by
the resolved as-of date against KnowledgeGraphProvision's effective date range.
"""

from pydantic import BaseModel

from app.services.rag.retriever.keyword_store import keyword_search
from app.services.rag.retriever.vector_store import similarity_search
from app.shared.schemas.tax_year import TaxYearContext


class RetrievedChunk(BaseModel):
    chunk_id: str
    source_id: str
    content: str
    section_reference: str | None = None
    score: float


async def hybrid_search(
    query: str, as_of: TaxYearContext, top_k: int = 10
) -> list[RetrievedChunk]:
    raise NotImplementedError(
        "TODO: run similarity_search + keyword_search concurrently, fuse "
        "with Reciprocal Rank Fusion, and return the top_k RetrievedChunk"
    )
