"""Retrieval entrypoint for the RAG path -- currently vector-only.

This was originally meant to run Reciprocal Rank Fusion over vector_store
(Pinecone) + keyword_store (Postgres full-text search over
KnowledgeGraphProvision). keyword_store.py is still correctly implemented
against the schema, but KnowledgeGraphProvision has 0 rows: the real
ingestion pipeline writes statutory content straight to Pinecone (vectors)
and Neo4j (structured rules), never into that table. Fusing against a
structurally-empty second source added complexity with no benefit, so this
calls similarity_search directly. If a keyword-searchable corpus is ever
populated into KnowledgeGraphProvision, reintroduce keyword_search here with
Reciprocal Rank Fusion.
"""

from pydantic import BaseModel

from app.services.rag.retriever.vector_store import similarity_search
from app.shared.embeddings.openai_embedding_provider import get_embedding_provider
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
    [query_embedding] = await get_embedding_provider().embed([query])
    results = await similarity_search(query_embedding, as_of, top_k)
    return [
        RetrievedChunk(
            chunk_id=row["chunk_id"],
            source_id=row["source_id"],
            content=row["content"],
            section_reference=row.get("section_reference"),
            score=row["score"],
        )
        for row in results
    ]
