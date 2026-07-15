"""Pinecone-backed similarity search over statutory knowledge-graph chunks.

Reads the `statutory-kg` namespace that ingestion/upsert/statutory_kg_upsert.py
writes -- the same chunk ids, so `chunk_id` joins a vector hit to the Neo4j
`VectorChunkRef` nodes graph_writer.py creates. Never touches `user-docs`; the
two namespaces are never mixed.

Goes through shared/vector/pinecone_client.py, the only file permitted to
import the Pinecone SDK, and shared/embeddings via ingestion/embedding.py for
the query vector. No SDK is imported here.

QUERY EMBEDDING MUST MATCH THE STORED EMBEDDING. Both sides go through
embed_texts(), so both get `text-embedding-3-large` truncated to
EMBEDDING_DIMENSIONS (1536), matching the index. If the model or dimension is
ever changed on one side only, Pinecone raises on a dimension mismatch -- but a
*model* change at the same dimension fails silently, returning plausible
nearest neighbours computed in an unrelated vector space. Re-verify the index
dimension against EMBEDDING_DIMENSIONS after any embedding config change.

NO AS-OF FILTER IS APPLIED, deliberately. The architecture calls for filtering
retrieval by the resolved as-of date, but every vector currently carries
`effective_from=''` and `regime='1961'` (api/admin.py upserts with only
`tier=10` and lets the rest default), so a metadata filter would match nothing
and silently empty the result set. Worse, the `regime` tag is not merely absent
but wrong: the corpus contains Income-tax Act 2025 provisions (sections above
298, which do not exist in the 1961 Act) all labelled '1961'. Filtering on it
would confidently return the wrong Act. `as_of` is therefore accepted and
unused here until the metadata is backfilled -- see filter_supported().

Consequence for callers: a vector hit is a POINTER, not an authority. The
corpus mixes vintages (the Sec 87A threshold appears as both the current
12,00,000 and the superseded 7,00,000, in the same document), and the Evidence
Gate cannot tell them apart -- it verifies provenance, not currency. Take the
chunk's topic; take figures from computation/rules/personal/slab_tables.py or
the Neo4j rule graph.
"""

from app.services.ingestion.embedding import embed_texts
from app.shared.schemas.tax_year import TaxYearContext
from app.shared.vector.pinecone_client import get_pinecone_client

STATUTORY_KG_NAMESPACE = "statutory-kg"


def filter_supported() -> bool:
    """Whether as-of/regime metadata filtering can be trusted yet.

    Hard False until ingestion backfills `effective_from`/`regime`. Kept as a
    function rather than a comment so the switch is discoverable from the
    callers that will want it.
    """
    return False


async def similarity_search(
    query: str, as_of: TaxYearContext, top_k: int = 10
) -> list[dict]:
    """Semantic search. Returns plain dicts; no Pinecone types leak out.

    `as_of` is part of the retrieval contract every store shares and is
    accepted for that consistency, but is not yet applied -- see the module
    docstring.
    """
    del as_of  # not usable until vector metadata is backfilled

    embeddings = await embed_texts([query])
    if not embeddings:
        return []

    hits = get_pinecone_client().query(
        namespace=STATUTORY_KG_NAMESPACE,
        vector=embeddings[0],
        top_k=top_k,
    )

    return [
        {
            "chunk_id": hit["id"],
            "source_id": hit["metadata"].get("source_id", ""),
            "content": hit["metadata"].get("text", ""),
            # Pinecone metadata carries no section number; only the Neo4j join
            # on chunk_id can supply one. See retriever/graph_store.py.
            "section_reference": None,
            "score": hit["score"],
        }
        for hit in hits
    ]
