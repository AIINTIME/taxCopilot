"""Neo4j read path over the structured rate-rule graph that
services/ingestion/kg_graph_extraction/graph_writer.py commits to (Section
--GOVERNS--> AssetClass, RateRule --SOURCED_FROM--> VectorChunkRef).

Sibling to vector_store.py -- one retrieval source per file. Imports
app.shared.graph.neo4j_client.get_neo4j_client() only, never the neo4j SDK
directly, preserving neo4j_client.py as the sole import site for that SDK.

Matching is fuzzy/keyword based, not an exact asset_class match: the
committed RateRule.asset_class values are free-text labels an LLM extracted
per statutory chunk during ingestion (e.g. "Long-term capital gains",
"Short-Term Gain", "Capital Assets to Indian Co."), not the normalized
values the computation engine uses ("other" / "listed_equity_or_equity_mf").
An exact match against those normalized values would never find anything
even though real, relevant rules exist in the live graph. See
services/rag/ground_truth_gate.py's derive_ground_truth_keywords for how
callers should build the `keywords` this expects.
"""

from app.shared.graph.neo4j_client import get_neo4j_client

_LOOKUP_RATE_RULE_QUERY = """
MATCH (r:RateRule)
WHERE any(kw IN $keywords WHERE toLower(r.asset_class) CONTAINS toLower(kw))
OPTIONAL MATCH (r)-[src:SOURCED_FROM]->(ref:VectorChunkRef)
RETURN r.section_number  AS section_number,
       r.asset_class     AS asset_class,
       r.effective_from  AS effective_from,
       r.rate            AS rate,
       r.indexation      AS indexation,
       r.condition_text  AS condition_text,
       r.selector        AS selector,
       ref.chunk_id      AS chunk_id,
       ref.document_id   AS document_id,
       src.evidence_span AS evidence_span
LIMIT $limit
"""


async def lookup_rate_rule(keywords: list[str], limit: int = 15) -> list[dict]:
    """Return every committed RateRule whose free-text asset_class contains
    any of `keywords` (case-insensitive substring match). Returns multiple
    candidates rather than requiring one exact hit -- ground_truth_gate.py
    reasons over all of them.
    """
    if not keywords:
        return []
    return await get_neo4j_client().run_read(
        _LOOKUP_RATE_RULE_QUERY,
        keywords=keywords,
        limit=limit,
    )
