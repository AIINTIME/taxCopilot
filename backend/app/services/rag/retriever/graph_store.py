"""Neo4j rule-graph lookups: the exact, structured "vectorless" path.

Goes through shared/graph/neo4j_client.py, the only file permitted to import
the neo4j SDK. Callers get plain dicts / Citation models; no driver types leak.

Queries must match the shape graph_writer.py MERGEs:

    (Section {number})-[:GOVERNS]->(AssetClass {name})
    (RateRule {section_number, asset_class, effective_from})
        -[:SOURCED_FROM {evidence_span, auto_approved, committed_at}]->
    (VectorChunkRef {chunk_id, document_id})

`VectorChunkRef.chunk_id` is the SAME id Pinecone stores, which is what makes
the two stores joinable: Pinecone finds a chunk semantically, this module turns
that chunk into the rules and verbatim evidence extracted from it. That join is
the whole point of the vector/vectorless split -- a stale chunk is still
reliable about WHICH section it concerns even when its figures are out of date,
so the vector store supplies the topic and the graph supplies the law.

TWO LIMITS TO KNOW (both real as of 2026-07-16, both Phase 4 work):

1. The graph holds no personal-tax rules. Committed sections include Sec 80C
   (1), 80D (1) and 24(b) (2), but Sec 115BAC, Sec 87A and Sec 16(ia) have
   ZERO. So citations_for_sections() returns [] for the sections a personal
   tax computation actually cites. That is a data gap, not a bug here.
2. Only 158 of 356 proposals were committed -- the rest failed the verbatim
   evidence-span check. Coverage is thin by construction.

Callers must therefore treat an empty result as normal and degrade gracefully,
never as an error.
"""

from app.shared.graph.neo4j_client import get_neo4j_client
from app.shared.schemas.citation import Citation
from app.shared.schemas.tax_year import TaxYearContext

# Graph-derived citations never pass through an LLM -- they are assembled from
# a SOURCED_FROM edge whose evidence_span was checked verbatim against the
# source chunk at ingestion. They cannot be hallucinated, so they are verified
# by construction and do not need the Evidence Gate (which exists to catch LLM
# invention). Kept below 1.0 because graph coverage is partial and the
# underlying chunk's currency is not guaranteed.
_GRAPH_CITATION_CONFIDENCE = 0.9

_RULES_FOR_SECTION = """
MATCH (r:RateRule {section_number: $section_number})
OPTIONAL MATCH (r)-[src:SOURCED_FROM]->(ref:VectorChunkRef)
RETURN r.section_number  AS section_number,
       r.asset_class     AS asset_class,
       r.rate            AS rate,
       r.indexation      AS indexation,
       r.condition_text  AS condition_text,
       r.selector        AS selector,
       r.effective_from  AS effective_from,
       ref.chunk_id      AS chunk_id,
       ref.document_id   AS document_id,
       src.evidence_span AS evidence_span
"""

_CITATIONS_FOR_SECTIONS = """
MATCH (r:RateRule)-[src:SOURCED_FROM]->(ref:VectorChunkRef)
WHERE r.section_number IN $section_numbers
  AND src.evidence_span IS NOT NULL
  AND src.evidence_span <> ''
RETURN DISTINCT
       r.section_number  AS section_number,
       ref.chunk_id      AS chunk_id,
       ref.document_id   AS document_id,
       src.evidence_span AS evidence_span
"""

_RULES_FOR_CHUNKS = """
MATCH (r:RateRule)-[src:SOURCED_FROM]->(ref:VectorChunkRef)
WHERE ref.chunk_id IN $chunk_ids
RETURN r.section_number  AS section_number,
       ref.chunk_id      AS chunk_id,
       src.evidence_span AS evidence_span
"""


async def rules_for_section(section_number: str, as_of: TaxYearContext) -> list[dict]:
    """Structured rules for a section. Empty list when the graph has none.

    `as_of` is accepted for contract symmetry with the other stores but not yet
    applied: RateRule.effective_from is written as a free-text string by
    graph_writer.py (whatever the LLM extracted, or ""), so it cannot be
    compared to a date without parsing it first. Filtering on it would drop
    valid rules. Deferred to Phase 4, which gives rules typed dates.
    """
    del as_of

    return await get_neo4j_client().run_read(
        _RULES_FOR_SECTION, section_number=section_number
    )


async def citations_for_sections(
    section_numbers: list[str], as_of: TaxYearContext
) -> list[Citation]:
    """Verbatim citations for the sections a computation trace referenced.

    This is what gives a computation-only answer real sources: the trace tags
    each step with a section, and each section resolves here to the evidence
    span a human could check.
    """
    del as_of

    if not section_numbers:
        return []

    rows = await get_neo4j_client().run_read(
        _CITATIONS_FOR_SECTIONS, section_numbers=list(section_numbers)
    )

    return [
        Citation(
            chunk_id=row["chunk_id"],
            source_id=row.get("document_id") or "",
            section_reference=row["section_number"],
            excerpt=row["evidence_span"],
            confidence=_GRAPH_CITATION_CONFIDENCE,
            verified=True,
        )
        for row in rows
    ]


async def sections_for_chunks(chunk_ids: list[str]) -> dict[str, str]:
    """Map Pinecone chunk ids -> the section their extracted rule cites.

    The join that lets a semantic hit acquire a section reference: Pinecone
    metadata carries no section number, so vector_store leaves
    `section_reference` None and hybrid_retriever backfills it from here.
    Chunks with no committed rule are simply absent from the mapping.
    """
    if not chunk_ids:
        return {}

    rows = await get_neo4j_client().run_read(
        _RULES_FOR_CHUNKS, chunk_ids=list(chunk_ids)
    )

    return {
        row["chunk_id"]: row["section_number"]
        for row in rows
        if row.get("chunk_id") and row.get("section_number")
    }
