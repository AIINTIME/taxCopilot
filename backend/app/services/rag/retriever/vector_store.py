"""pgvector-backed similarity search over statutory knowledge-graph chunks.

Uses the existing Prisma client (app.db.prisma) via raw SQL rather than a new
DB driver/connection -- consistent with the rest of the app's single-Prisma-
client pattern.

TODO: this scaffold does not yet add a chunk/embedding table to
prisma/schema.prisma, nor enable the `vector` Postgres extension -- both are
deferred to the actual RAG implementation. KnowledgeGraphProvision currently
only stores provision metadata + content, not embeddings.
"""

from app.db import prisma
from app.shared.schemas.tax_year import TaxYearContext


async def similarity_search(
    query_embedding: list[float], as_of: TaxYearContext, top_k: int = 10
) -> list[dict]:
    raise NotImplementedError(
        "TODO: prisma.query_raw(...) a pgvector cosine-distance search over "
        "the (not-yet-created) chunk-embedding table, filtered by "
        "KnowledgeGraphProvision effectiveFrom/effectiveTo for as_of.as_of_date"
    )
