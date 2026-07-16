"""Evidence Gate: verifies every citation the LLM produced against the
actually-retrieved chunks. Unverifiable citations are stripped from the
response AND the query is flagged for human review -- never silently
dropped.
"""

import re

from app.services.rag.retriever.hybrid_retriever import RetrievedChunk
from app.shared.schemas.audit_entry import GateStatusLiteral
from app.shared.schemas.citation import Citation

INSUFFICIENT_SOURCES_MESSAGE = (
    "This query requires sources not currently in the Knowledge Graph — "
    "consult a domain expert."
)

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")
_WORD_PATTERN = re.compile(r"[a-zA-Z]{4,}")
_SUPPORT_THRESHOLD = 0.5

# Key-fact extraction: numbers and section references are the highest-risk
# content to get wrong, so they get an exact (normalized) traceability check
# instead of relying on general word-overlap. A statutory section reference
# needs either a letter suffix (115JB, 115BAA) or a parenthetical sub-clause
# (32(1)(iia)) to count -- a bare 2-3 digit number ("20", "2024") is too
# noisy (years, unrelated figures) to treat as a section reference.
_SECTION_REFERENCE_PATTERN = re.compile(
    r"\b\d{2,3}[A-Za-z]{1,4}(?:\(\d+\)(?:\([a-z]+\))?)?\b"
    r"|\b\d{2,3}\(\d+\)(?:\([a-z]+\))?\b"
)
_PERCENTAGE_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*(?:%|percent)", re.IGNORECASE)
_MONETARY_PATTERN = re.compile(
    r"(?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d+)?|\b[\d,]+(?:\.\d+)?\s*(?:crores?|lakhs?)\b",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _extract_key_facts(text: str) -> list[str]:
    """Specific, checkable facts (section refs, rates, amounts) an excerpt
    makes -- each one must be verbatim-traceable to the source chunk."""
    facts: list[str] = []
    for pattern in (_SECTION_REFERENCE_PATTERN, _PERCENTAGE_PATTERN, _MONETARY_PATTERN):
        facts.extend(match.group(0) for match in pattern.finditer(text))
    return [_normalize(fact) for fact in facts]


def extract_citations(text: str, retrieved_chunks: list[RetrievedChunk]) -> list[Citation]:
    """Pull every [N] marker out of the narrative text and pair it with the
    sentence/clause it's attached to (the "excerpt" to verify). N is a
    1-based index into retrieved_chunks (see prompts.build_context_block),
    not the raw chunk_id -- short numeric tokens are reproduced far more
    reliably by the model than long alphanumeric chunk_ids."""
    citations: list[Citation] = []

    for match in _CITATION_PATTERN.finditer(text):
        index = int(match.group(1))
        preceding = text[: match.start()]
        boundary = max(preceding.rfind(". "), preceding.rfind("\n")) + 1
        # When two or more [N] markers are stacked back-to-back on one clause
        # (e.g. "...text [1][3]."), a later marker's excerpt window includes
        # the earlier marker's literal "[1]" text -- strip any such stray
        # citation tokens out, since real prose never legitimately contains
        # a bare "[N]" as content.
        excerpt = _CITATION_PATTERN.sub("", text[boundary : match.start()]).strip()
        chunk = (
            retrieved_chunks[index - 1] if 1 <= index <= len(retrieved_chunks) else None
        )

        citations.append(
            Citation(
                chunk_id=chunk.chunk_id if chunk else f"invalid-citation-index-{index}",
                source_id=chunk.source_id if chunk else "",
                document_id=chunk.document_id if chunk else None,
                section_reference=chunk.section_reference if chunk else None,
                excerpt=excerpt,
                confidence=1.0 if chunk else 0.0,
                verified=False,
            )
        )

    return citations


def _excerpt_supported_by_chunk(excerpt: str, chunk_content: str) -> bool:
    key_facts = _extract_key_facts(excerpt)
    if key_facts:
        # Every specific number/section reference the excerpt cites must be
        # verbatim-traceable to the chunk -- a topically-similar chunk that
        # doesn't actually contain the cited rate/section must fail here,
        # regardless of how much surrounding vocabulary it shares.
        normalized_chunk = _normalize(chunk_content)
        return all(fact in normalized_chunk for fact in key_facts)

    excerpt_words = {w.lower() for w in _WORD_PATTERN.findall(excerpt)}
    if not excerpt_words:
        return False
    content_words = {w.lower() for w in _WORD_PATTERN.findall(chunk_content)}
    overlap = excerpt_words & content_words
    return len(overlap) / len(excerpt_words) >= _SUPPORT_THRESHOLD


def verify_citations(
    citations: list[Citation], retrieved_chunks: list[RetrievedChunk]
) -> tuple[list[Citation], GateStatusLiteral]:
    if not citations:
        return [], "FLAGGED"

    chunk_lookup = {c.chunk_id: c for c in retrieved_chunks}
    verified_citations: list[Citation] = []

    for citation in citations:
        chunk = chunk_lookup.get(citation.chunk_id)
        is_verified = chunk is not None and _excerpt_supported_by_chunk(
            citation.excerpt, chunk.content
        )
        verified_citations.append(citation.model_copy(update={"verified": is_verified}))

    verified_count = sum(1 for c in verified_citations if c.verified)
    if verified_count == len(verified_citations):
        gate_status: GateStatusLiteral = "VERIFIED"
    elif verified_count == 0:
        gate_status = "FLAGGED"
    else:
        gate_status = "PARTIAL"

    return verified_citations, gate_status


def strip_unverified_claims(text: str, citations: list[Citation]) -> str:
    """Replace each unverified citation's claim with the honest fallback
    sentence instead of silently deleting it -- the user must see that
    something was removed, not get a seamlessly-shortened answer.

    Matches generically on the excerpt followed by a RUN of one-or-more [N]
    markers (the LLM sometimes stacks several, e.g. "...text [1][3]." when
    citing two chunks for one clause), not just a single marker -- otherwise
    a trailing marker from a second, sibling citation is left dangling in
    the output. If a clause carries multiple stacked citations and even one
    of them fails verification, the whole clause is replaced: there's no
    clean way to show "half-verified" prose, and erring toward stripping
    matches this system's "never silently under-verify" stance. Excerpts
    are deduplicated so a shared clause is only substituted once even
    though multiple citations may carry the identical excerpt text."""
    result = text
    already_stripped: set[str] = set()

    for citation in citations:
        if citation.verified:
            continue
        if not citation.excerpt or citation.excerpt in already_stripped:
            continue
        claim_pattern = re.compile(
            re.escape(citation.excerpt) + r"\s*(?:\[\d+\]\s*)+\.?"
        )
        if claim_pattern.search(result):
            result = claim_pattern.sub(INSUFFICIENT_SOURCES_MESSAGE, result)
            already_stripped.add(citation.excerpt)
        # No match found for this excerpt -- leave as-is rather than risk
        # stripping the wrong bracketed number elsewhere in the text.

    # Two or more DIFFERENT unverified excerpts each get replaced with the
    # identical fallback message above -- when those excerpts were adjacent
    # in the original text, that leaves the same sentence repeated
    # back-to-back. Collapse only consecutive repeats (not ones separated by
    # other verified content, which are legitimately distinct flags).
    result = re.sub(
        rf"(?:{re.escape(INSUFFICIENT_SOURCES_MESSAGE)}\s*){{2,}}",
        INSUFFICIENT_SOURCES_MESSAGE + " ",
        result,
    ).strip()
    return result
