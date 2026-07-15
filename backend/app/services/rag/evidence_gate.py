"""Evidence Gate: verifies every citation the LLM produced against the
actually-retrieved chunks. Unverifiable citations are stripped from the
response AND the query is flagged for human review -- never silently
dropped.

Mirrors the discipline ingestion already applies in
kg_graph_extraction/rule_proposal.py's verify_evidence_span: an excerpt must
appear verbatim in its source, case-insensitively, or it does not count. Same
rule, opposite end of the pipeline -- there it guards what enters the graph,
here it guards what reaches the user.

WHAT THIS GATE CANNOT DO -- important, and easy to over-trust. It verifies
PROVENANCE, not CURRENCY. It answers "did this claim really come from a chunk
we retrieved?", never "is that chunk still good law?". The corpus contains both
the current Sec 87A threshold (12,00,000) and the superseded one (7,00,000), in
the same document, with no metadata distinguishing them, so a stale claim
passes this gate cleanly -- it genuinely is in the corpus. Staleness is
addressed elsewhere: figures come from computation/rules/personal/slab_tables.py
and the dated rule graph, never from a narrated chunk, and rag/prompts forbids
the model from emitting figures at all.

The gate also does not apply to graph-derived citations
(retriever/graph_store.citations_for_sections). Those are assembled from a
SOURCED_FROM edge whose evidence_span was already checked verbatim at
ingestion and never pass through an LLM, so they are verified by construction.
Keep the two paths distinct.
"""

from app.services.rag.retriever.hybrid_retriever import RetrievedChunk
from app.shared.schemas.audit_entry import GateStatusLiteral
from app.shared.schemas.citation import Citation


def _normalise(text: str) -> str:
    """Collapse whitespace so a re-wrapped quote still matches its source.

    Chunk text carries PDF line breaks mid-sentence; an LLM quoting it will
    usually normalise those. Without this, correct citations would be stripped
    for cosmetic reasons and every answer would read as FLAGGED.
    """
    return " ".join(text.lower().split())


def _is_supported(citation: Citation, chunks_by_id: dict[str, str]) -> bool:
    content = chunks_by_id.get(citation.chunk_id)
    if content is None:
        # Cites a chunk that was never retrieved for THIS query -- the
        # signature of an invented or mis-remembered source.
        return False

    excerpt = _normalise(citation.excerpt)
    if not excerpt:
        return False

    return excerpt in _normalise(content)


def verify_citations(
    citations: list[Citation], retrieved_chunks: list[RetrievedChunk]
) -> tuple[list[Citation], GateStatusLiteral]:
    """Return (surviving citations, gate status).

    VERIFIED -- every citation checked out (or there were none to check).
    PARTIAL  -- some survived, some were stripped.
    FLAGGED  -- citations were offered and none survived; the answer rests on
                nothing retrievable and needs a human. Surfaced to the user as
                "review required".
    """
    if not citations:
        # No claims to attribute. Vacuously fine -- a clarifying question or a
        # pure computation asserts nothing that needs a source.
        return [], "VERIFIED"

    chunks_by_id = {chunk.chunk_id: chunk.content for chunk in retrieved_chunks}

    verified: list[Citation] = []
    stripped = 0

    for citation in citations:
        if _is_supported(citation, chunks_by_id):
            verified.append(citation.model_copy(update={"verified": True}))
        else:
            stripped += 1

    if stripped == 0:
        return verified, "VERIFIED"
    if verified:
        return verified, "PARTIAL"
    return [], "FLAGGED"
