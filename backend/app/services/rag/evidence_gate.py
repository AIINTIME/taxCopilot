"""Evidence Gate: verifies every citation the LLM produced against the
actually-retrieved chunks. Unverifiable citations are stripped from the
response AND the query is flagged for human review -- never silently
dropped.
"""

from app.services.rag.retriever.hybrid_retriever import RetrievedChunk
from app.shared.schemas.citation import Citation
from app.shared.schemas.audit_entry import GateStatusLiteral


def verify_citations(
    citations: list[Citation], retrieved_chunks: list[RetrievedChunk]
) -> tuple[list[Citation], GateStatusLiteral]:
    if not citations:
        return [], "VERIFIED"

    chunks_by_id = {chunk.chunk_id: chunk for chunk in retrieved_chunks}
    verified_citations: list[Citation] = []
    any_stripped = False

    for citation in citations:
        chunk = chunks_by_id.get(citation.chunk_id)
        supported = chunk is not None and citation.excerpt.lower() in chunk.content.lower()
        if supported:
            verified_citations.append(citation.model_copy(update={"verified": True}))
        else:
            any_stripped = True

    if not any_stripped:
        return verified_citations, "VERIFIED"
    if verified_citations:
        return verified_citations, "PARTIAL"
    return verified_citations, "FLAGGED"
