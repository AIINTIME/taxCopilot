"""BM25-style keyword search via Postgres full-text search, using the
existing Prisma client (app.db.prisma) via raw SQL -- no new DB driver.

NOT currently called by hybrid_retriever.py: KnowledgeGraphProvision has 0
rows in the live database -- the real ingestion pipeline writes statutory
content straight to Pinecone (vectors) and Neo4j (structured rules), never
into this table. This function is still correct against the schema and
ready to be wired back in (with Reciprocal Rank Fusion against
vector_store.py) if that table ever gets populated.
"""

from datetime import datetime

from app.db import prisma
from app.shared.schemas.tax_year import TaxYearContext

# Provision-level (not chunk-level) full-text search -- no separate chunk id
# exists for a keyword hit, so the provision's own id stands in for chunk_id,
# matching vector_store.py's output shape for hybrid_retriever.py's fusion.
_KEYWORD_SEARCH_QUERY = """
SELECT p.id       AS chunk_id,
       p."sourceId" AS source_id,
       p.content  AS content,
       NULL       AS section_reference,
       ts_rank(to_tsvector('english', p.content), plainto_tsquery('english', $1)) AS score
FROM "KnowledgeGraphProvision" p
WHERE p.regime = $2::"TaxActRegime"
  AND p.status = 'ACTIVE'
  AND p."effectiveFrom" <= $3::timestamp
  AND (p."effectiveTo" IS NULL OR p."effectiveTo" >= $3::timestamp)
  AND to_tsvector('english', p.content) @@ plainto_tsquery('english', $1)
ORDER BY score DESC
LIMIT $4
"""


async def keyword_search(
    query: str, as_of: TaxYearContext, top_k: int = 10
) -> list[dict]:
    return await prisma.query_raw(
        _KEYWORD_SEARCH_QUERY,
        query,
        as_of.regime.name,
        datetime.combine(as_of.as_of_date, datetime.min.time()),
        top_k,
    )
