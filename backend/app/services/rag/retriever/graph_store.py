"""Neo4j read paths over the structured rate-rule graph that
services/ingestion/kg_graph_extraction/graph_writer.py commits to (Section
--GOVERNS--> AssetClass, RateRule --SOURCED_FROM--> VectorChunkRef).

Sibling to vector_store.py -- one retrieval source per file. Imports
app.shared.graph.neo4j_client.get_neo4j_client() only, never the neo4j SDK
directly, preserving neo4j_client.py as the sole import site for that SDK.

Two independent read paths live here:

- `lookup_rate_rule` -- fuzzy/keyword matching used by the ground-truth
  check in orchestration/graphs/query_graph.py. The committed
  RateRule.asset_class values are free-text labels an LLM extracted per
  statutory chunk during ingestion (e.g. "Long-term capital gains",
  "Short-Term Gain", "Capital Assets to Indian Co."), not the normalized
  values the computation engine uses ("other" / "listed_equity_or_equity_mf").
  An exact match against those normalized values would never find anything
  even though real, relevant rules exist in the live graph. See
  services/rag/ground_truth_gate.py's derive_ground_truth_keywords for how
  callers should build the `keywords` this expects.

- `structured_search` -- deterministic section-number / asset-class hint
  matching over the same graph, used by hybrid_retriever.py's Reciprocal
  Rank Fusion alongside vector_store.py's semantic search. These are exact
  statutory facts, not fuzzy semantic matches, so no embedding is used here.
"""

import re

from app.shared.graph.neo4j_client import get_neo4j_client
from app.shared.schemas.tax_year import TaxYearContext

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


_SECTION_HINT_PATTERN = re.compile(r"\b\d{2,3}[A-Za-z]{0,4}(?:\(\d+\)(?:\([a-z]+\))?)?\b")
_STOPWORDS = {
    "what", "when", "where", "which", "does", "that", "this", "with", "from",
    "have", "about", "under", "explain", "define", "section", "would", "should",
    "please", "there", "their", "applicable", "provisions", "conditions",
}


def _extract_hints(query: str) -> tuple[list[str], list[str]]:
    section_hints = [m.group(0) for m in _SECTION_HINT_PATTERN.finditer(query)]
    keywords = [
        w.lower()
        for w in re.findall(r"[a-zA-Z]{4,}", query)
        if w.lower() not in _STOPWORDS
    ]
    return section_hints, keywords


_STRUCTURED_QUERY = """
MATCH (r:RateRule)-[src:SOURCED_FROM]->(ref:VectorChunkRef)
WHERE (size($section_hints) = 0 AND size($keywords) = 0)
   OR any(hint IN $section_hints WHERE toLower(r.section_number) CONTAINS toLower(hint))
   OR any(word IN $keywords WHERE toLower(r.asset_class) CONTAINS word
                              OR toLower(coalesce(r.condition_text, '')) CONTAINS word)
RETURN r.section_number AS section_number, r.asset_class AS asset_class, r.rate AS rate,
       r.indexation AS indexation, r.condition_text AS condition_text,
       src.evidence_span AS evidence_span, ref.chunk_id AS chunk_id,
       ref.document_id AS document_id
LIMIT $top_k
"""


async def structured_search(
    query: str, as_of: TaxYearContext, top_k: int = 10
) -> list[dict]:
    section_hints, keywords = _extract_hints(query)

    rows = await get_neo4j_client().run_read(
        _STRUCTURED_QUERY,
        section_hints=section_hints,
        keywords=keywords,
        top_k=top_k,
    )

    return [
        {
            "chunk_id": row["chunk_id"],
            "source_id": row["document_id"] or "",
            "document_id": row["document_id"] or "",
            "content": row["evidence_span"]
            or f"Section {row['section_number']}: {row['asset_class']} — rate {row['rate']}"
            f"{', condition: ' + row['condition_text'] if row['condition_text'] else ''}",
            "section_reference": row["section_number"],
            "score": 1.0,
        }
        for row in rows
    ]
