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
    raise NotImplementedError(
        "TODO: for each citation, confirm chunk_id is present in "
        "retrieved_chunks and the excerpt is actually supported by that "
        "chunk's content. Strip unverifiable citations; return gate_status="
        "'FLAGGED' (never silently drop) if any were stripped, else "
        "'VERIFIED' (or 'PARTIAL' if some citations were unverifiable but "
        "others verified)"
    )
