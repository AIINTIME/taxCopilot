"""BM25-style keyword search via Postgres full-text search, using the
existing Prisma client (app.db.prisma) via raw SQL -- no new DB driver.

One of the two "vectorless" paths: exact lexical matching over
KnowledgeGraphProvision, which -- unlike the Pinecone metadata -- does carry
real `effectiveFrom`/`effectiveTo`/`regime`/`status` columns, so this store CAN
honour the resolved as-of date, and does.

REGIME VALUE MAPPING -- easy to get wrong. The Prisma enum stores member NAMES
('ACT_1961', 'ACT_2025'), while shared/schemas/tax_year.TaxActRegime carries
values ('1961', '2025'). SQL comparisons must therefore use `.name`, never
`.value`. (The same mismatch is a latent bug in
ingestion/upsert/statutory_kg_upsert.py's upsert_provision, which passes
`regime.value` into this Prisma enum column; it has never fired only because
that function has no callers yet.)

CURRENT REALITY: KnowledgeGraphProvision has 0 rows. Nothing writes it --
api/admin.py's upload path targets Pinecone and Neo4j only, and the
gov_scraper that would call upsert_provision is still a stub. This store is
therefore correct but inert: hybrid_search will fan out to it and get nothing
until provisions are ingested. Implemented now so the fusion has its third leg
ready and nothing else changes the day provisions land.
"""

from app.db import prisma
from app.shared.schemas.tax_year import TaxYearContext

_SEARCH_SQL = """
SELECT
    id,
    "sourceId"  AS source_id,
    content,
    ts_rank(
        to_tsvector('english', content),
        plainto_tsquery('english', $1)
    ) AS score
FROM "KnowledgeGraphProvision"
WHERE status = 'ACTIVE'
  AND regime = CAST($2 AS "TaxActRegime")
  AND "effectiveFrom" <= CAST($3 AS TIMESTAMP)
  AND ("effectiveTo" IS NULL OR "effectiveTo" >= CAST($3 AS TIMESTAMP))
  AND to_tsvector('english', content) @@ plainto_tsquery('english', $1)
ORDER BY score DESC
LIMIT $4
"""


async def keyword_search(
    query: str, as_of: TaxYearContext, top_k: int = 10
) -> list[dict]:
    """Full-text search over provisions in force on the resolved as-of date.

    Returns plain dicts shaped like vector_store.similarity_search's, so
    hybrid_retriever can fuse the two without special-casing either.
    """
    rows = await prisma.query_raw(
        _SEARCH_SQL,
        query,
        as_of.regime.name,
        # Passed as an ISO string and cast in SQL: prisma.query_raw cannot
        # serialize a datetime.date parameter ("Type <class 'datetime.date'>
        # not serializable"), and the failure is easy to miss because
        # hybrid_retriever degrades a failing leg to empty.
        as_of.as_of_date.isoformat(),
        top_k,
    )

    return [
        {
            "chunk_id": row["id"],
            "source_id": row["source_id"],
            "content": row["content"],
            "section_reference": row["source_id"],
            "score": float(row["score"]),
        }
        for row in rows
    ]
