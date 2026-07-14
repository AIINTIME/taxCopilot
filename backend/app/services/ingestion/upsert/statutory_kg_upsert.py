"""Upserts statutory content into the permanent knowledge-graph.

Two write paths:

upsert_chunk_to_statutory_kg — used by the admin document-upload endpoint.
    Embeds a single text chunk and upserts it to the Pinecone "statutory-kg"
    namespace. This is the ONLY function allowed to write to that namespace.
    Never writes to "user-docs".

upsert_provision — kept for scraper-based ingestion (full regime/date metadata
    available). Writes a KnowledgeGraphProvision row to Postgres for RAG
    date-range filtering.
"""

from datetime import date

from app.db import prisma
from app.services.ingestion.embedding import embed_texts
from app.shared.schemas.tax_year import TaxActRegime
from app.shared.vector.pinecone_client import get_pinecone_client

STATUTORY_KG_NAMESPACE = "statutory-kg"


async def upsert_chunk_to_statutory_kg(
    chunk_id: str,
    chunk_text: str,
    document_id: str,
    source_id: str,
    tier: int,
    regime: TaxActRegime = TaxActRegime.ACT_1961,
    effective_from: date | None = None,
) -> None:
    [vector] = await embed_texts([chunk_text])

    get_pinecone_client().upsert(
        namespace=STATUTORY_KG_NAMESPACE,
        vectors=[
            {
                "id": chunk_id,
                "values": vector,
                "metadata": {
                    "document_id": document_id,
                    "source_id": source_id,
                    "tier": tier,
                    "regime": regime.value,
                    "effective_from": effective_from.isoformat() if effective_from else "",
                    "text": chunk_text[:1000],
                },
            }
        ],
    )


async def upsert_provision(
    source_id: str,
    regime: TaxActRegime,
    tier: int,
    effective_from: date,
    content: str,
    effective_to: date | None = None,
) -> str:
    existing = await prisma.knowledgegraphprovision.find_first(
        where={"sourceId": source_id, "status": "ACTIVE"}
    )
    if existing:
        await prisma.knowledgegraphprovision.update(
            where={"id": existing.id}, data={"status": "SUPERSEDED"}
        )

    provision = await prisma.knowledgegraphprovision.create(
        data={
            "sourceId": source_id,
            "regime": regime.value,
            "tier": tier,
            "effectiveFrom": effective_from,
            "effectiveTo": effective_to,
            "status": "ACTIVE",
            "content": content,
        }
    )
    return provision.id
