"""Structured (\"vectorless\") reads over the Neo4j rule graph populated by
ingestion (app/services/ingestion/kg_graph_extraction/graph_writer.py).

Deterministic text matching against section numbers / asset-class keywords
mentioned in the query -- these are exact statutory facts, not fuzzy
semantic matches, so no embedding is used here.
"""

import re

from app.shared.graph.neo4j_client import get_neo4j_client
from app.shared.schemas.tax_year import TaxYearContext

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
