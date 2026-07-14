"""Upserts a parsed statutory source into the permanent knowledge-graph
namespace (KnowledgeGraphProvision), using the existing Prisma client.
"""

from datetime import date

from app.db import prisma
from app.shared.schemas.tax_year import TaxActRegime


async def upsert_provision(
    source_id: str,
    regime: TaxActRegime,
    tier: int,
    effective_from: date,
    content: str,
    effective_to: date | None = None,
) -> str:
    raise NotImplementedError(
        "TODO: prisma.knowledgegraphprovision.create(data={...}) (or "
        "supersede the prior active row for source_id, per status="
        "'SUPERSEDED') and return the new row's id"
    )
