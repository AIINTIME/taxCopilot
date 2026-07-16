"""Reciprocal Rank Fusion of vector_store (semantic, Pinecone) + graph_store
(structured, Neo4j) results, filtered by the resolved as-of date/regime.
"""

import asyncio

from pydantic import BaseModel

from app.services.rag.retriever.graph_store import structured_search
from app.services.rag.retriever.vector_store import embed_query, similarity_search
from app.shared.schemas.tax_year import TaxYearContext

# Standard RRF damping constant -- large enough that a single source's rank-1
# result doesn't automatically dominate a result found by both sources.
_RRF_K = 60


class RetrievedChunk(BaseModel):
    chunk_id: str
    source_id: str
    document_id: str | None = None
    content: str
    section_reference: str | None = None
    score: float


async def hybrid_search(
    query: str, as_of: TaxYearContext, top_k: int = 10
) -> list[RetrievedChunk]:
    query_embedding = await embed_query(query)
    vector_results, structured_results = await asyncio.gather(
        similarity_search(query_embedding, as_of, top_k=top_k),
        structured_search(query, as_of, top_k=top_k),
    )

    rrf_scores: dict[str, float] = {}
    chunk_data: dict[str, dict] = {}

    for rank_list in (vector_results, structured_results):
        for rank, item in enumerate(rank_list, start=1):
            chunk_id = item["chunk_id"]
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
            chunk_data.setdefault(chunk_id, item)

    ranked_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)[:top_k]

    return [
        RetrievedChunk(
            chunk_id=cid,
            source_id=chunk_data[cid]["source_id"],
            document_id=chunk_data[cid].get("document_id"),
            content=chunk_data[cid]["content"],
            section_reference=chunk_data[cid]["section_reference"],
            score=rrf_scores[cid],
        )
        for cid in ranked_ids
    ]
