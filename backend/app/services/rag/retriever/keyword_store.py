"""BM25-style keyword search via Postgres full-text search, using the
existing Prisma client (app.db.prisma) via raw SQL -- no new DB driver.
"""

from app.db import prisma
from app.shared.schemas.tax_year import TaxYearContext


async def keyword_search(
    query: str, as_of: TaxYearContext, top_k: int = 10
) -> list[dict]:
    raise NotImplementedError(
        "TODO: prisma.query_raw(...) a Postgres ts_vector/ts_rank search over "
        "KnowledgeGraphProvision.content, filtered by effectiveFrom/effectiveTo "
        "for as_of.as_of_date"
    )
