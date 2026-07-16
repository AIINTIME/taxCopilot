"""Resolves a citation's document_id (the Prisma Document row it came from)
to a human-readable filename, so the UI can show a real document name instead
of the internal content-hash source_id.
"""

from app.db import prisma
from app.shared.schemas.citation import Citation


async def resolve_document_names(citations: list[Citation]) -> list[Citation]:
    document_ids = {c.document_id for c in citations if c.document_id}
    if not document_ids:
        return citations

    documents = await prisma.document.find_many(where={"id": {"in": list(document_ids)}})
    filename_by_id = {doc.id: doc.filename for doc in documents}

    return [
        citation.model_copy(update={"document_name": filename_by_id[citation.document_id]})
        if citation.document_id and citation.document_id in filename_by_id
        else citation
        for citation in citations
    ]
