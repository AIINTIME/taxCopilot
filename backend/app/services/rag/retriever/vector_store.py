"""Similarity search over the statutory knowledge namespace in Pinecone --
the real, already-populated vector store (shared/vector/pinecone_client.py,
"statutory-kg" namespace). An earlier version of this file queried a
pgvector table (KnowledgeChunk) invented from a stale architecture-doc
comment; that table was always empty and has been dropped (migration
202607160002) -- Pinecone was the real store all along.

pinecone_client.py's query() is a synchronous SDK call; run via
asyncio.to_thread so it doesn't block the event loop.
"""

import asyncio

from app.shared.embeddings.openai_embedding_provider import get_embedding_provider
from app.shared.schemas.tax_year import TaxYearContext
from app.shared.vector.pinecone_client import get_pinecone_client

_NAMESPACE = "statutory-kg"


async def similarity_search(
    query_embedding: list[float], as_of: TaxYearContext, top_k: int = 10
) -> list[dict]:
    # Deliberately no server-side regime filter: the ingested corpus so far
    # is tagged regime="1961" even for queries that resolve to the 2025-Act
    # regime (e.g. today's date), and Pinecone's metadata filter would
    # silently return nothing rather than degrade gracefully. Regime is
    # still returned per-row so callers/ground_truth_gate can reason about
    # it explicitly instead of it being invisibly filtered away.
    results = await asyncio.to_thread(
        get_pinecone_client().query,
        namespace=_NAMESPACE,
        vector=query_embedding,
        top_k=top_k,
    )
    return [
        {
            "chunk_id": row["id"],
            "source_id": row["metadata"].get("source_id", ""),
            "document_id": row["metadata"].get("document_id", ""),
            "content": row["metadata"].get("text", ""),
            "section_reference": row["metadata"].get("section_reference"),
            "score": row["score"],
            "regime": row["metadata"].get("regime"),
            "tier": row["metadata"].get("tier"),
        }
        for row in results
    ]


async def embed_query(query: str) -> list[float]:
    [vector] = await get_embedding_provider().embed([query])
    return vector
