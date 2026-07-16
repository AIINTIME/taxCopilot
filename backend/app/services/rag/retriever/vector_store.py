"""Pinecone-backed semantic similarity search over the statutory-kg namespace.

The scaffold this replaces targeted pgvector, but the ingestion pipeline
(app/services/ingestion/upsert/statutory_kg_upsert.py) writes real chunks to
Pinecone's "statutory-kg" namespace -- this redirects retrieval to match.
"""

from app.shared.embeddings.openai_embedding_provider import get_embedding_provider
from app.shared.schemas.tax_year import TaxYearContext
from app.shared.vector.pinecone_client import get_pinecone_client

STATUTORY_KG_NAMESPACE = "statutory-kg"


async def similarity_search(
    query_embedding: list[float], as_of: TaxYearContext, top_k: int = 10
) -> list[dict]:
    # NOT filtering by regime here, deliberately. The admin upload endpoint
    # (app/api/admin.py) never passes a regime when ingesting -- every chunk
    # defaults to ACT_1961 regardless of actual content. An exact-match
    # filter against a tag that isn't meaningfully populated doesn't narrow
    # results, it silently discards all of them: confirmed in practice that
    # any query resolving to ACT_2025 (i.e. any query today, since the
    # 1-Apr-2026 pivot has passed) returned zero matches against a
    # 4,198-vector index. Re-enable this filter once ingestion actually
    # tags regime per document; `as_of` is kept in the signature for that.
    matches = get_pinecone_client().query(
        namespace=STATUTORY_KG_NAMESPACE,
        vector=query_embedding,
        top_k=top_k,
    )
    return [
        {
            "chunk_id": m["id"],
            "source_id": m["metadata"].get("source_id", ""),
            "document_id": m["metadata"].get("document_id", ""),
            "content": m["metadata"].get("text", ""),
            "section_reference": None,
            "score": m["score"],
        }
        for m in matches
    ]


async def embed_query(query: str) -> list[float]:
    [vector] = await get_embedding_provider().embed([query])
    return vector
