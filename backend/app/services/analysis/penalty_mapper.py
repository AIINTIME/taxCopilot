"""Maps a discrepancy to the statutory penalty it exposes the filer to.

Neo4j lookup ONLY. A penalty claim is the most legally loaded thing this
product says -- "you may owe 200% of the tax sought to be evaded" is not a
sentence to derive from an embedding hit or a model's recollection. Every
penalty returned here must trace to a PenaltyRule committed to the rule graph,
whose evidence_span was checked verbatim against ingested statutory text at
extraction time. No graph rule, no penalty. Silence is the correct output when
the graph cannot support a claim.

CURRENT STATE (2026-07-16): this returns nothing, for two stacked reasons.

  1. The graph has no PenaltyRule nodes at all. The extraction schema in
     kg_graph_extraction/rule_proposal.py asks for a tax RATE rule
     (asset_class / rate / indexation) -- a shape that cannot express "Sec 270A:
     50% of tax on under-reported income". Penalty extraction is Phase 4.
  2. The Aura instance is paused, so even the queries that exist cannot run.

`23 Penalties & Prosecution.pdf` is already ingested (118 chunks) and is the
natural seed corpus once Phase 4 gives the graph a shape that can hold this.

Until then callers get an empty list and must present findings WITHOUT penalty
exposure rather than substituting a plausible one.
"""

import asyncio
import logging
from dataclasses import dataclass

from app.services.analysis.reconciler import Discrepancy, DiscrepancyType
from app.shared.graph.neo4j_client import get_neo4j_client
from app.shared.schemas.tax_year import TaxYearContext

logger = logging.getLogger(__name__)

# Same bound as the retriever's graph legs: the neo4j driver retries a paused
# Aura with backoff for up to 30s (measured), and a penalty annotation is never
# worth stalling a report for.
PENALTY_LOOKUP_TIMEOUT_S = 2.0

# Which statutory penalty provisions each kind of finding could engage. This is
# a ROUTING hint -- it decides which sections to look up, never what they say.
# The quantum, the trigger and the wording all come from the graph.
_CANDIDATE_SECTIONS: dict[DiscrepancyType, tuple[str, ...]] = {
    DiscrepancyType.EXCESS_DEDUCTION: ("270A", "Sec 270A"),
    DiscrepancyType.DISALLOWED_DEDUCTION: ("270A", "Sec 270A"),
    DiscrepancyType.TAX_MISMATCH: ("270A", "Sec 270A", "234B", "Sec 234B"),
    # Choosing a costlier regime is lawful. There is no penalty and there must
    # never appear to be one.
    DiscrepancyType.SUBOPTIMAL_REGIME: (),
}

_PENALTY_QUERY = """
MATCH (p:PenaltyRule)-[src:SOURCED_FROM]->(ref:VectorChunkRef)
WHERE p.section_number IN $sections
  AND src.evidence_span IS NOT NULL
  AND src.evidence_span <> ''
RETURN DISTINCT
       p.section_number  AS section_number,
       p.quantum         AS quantum,
       p.trigger         AS trigger,
       ref.chunk_id      AS chunk_id,
       src.evidence_span AS evidence_span
"""


@dataclass(frozen=True)
class PenaltyExposure:
    discrepancy_type: DiscrepancyType
    section_reference: str
    quantum: str
    trigger: str
    evidence_span: str
    chunk_id: str
    disclaimer: str = (
        "Indicative only, based on the statutory text on record. Whether a "
        "penalty applies depends on facts and intent that this analysis cannot "
        "assess. Have a qualified tax professional review before acting."
    )


async def penalties_for(
    discrepancies: list[Discrepancy], as_of: TaxYearContext
) -> list[PenaltyExposure]:
    """Statutory penalties the graph can actually support for these findings.

    Returns [] when the graph holds nothing relevant -- which is the case
    today, and is a correct, safe answer rather than a failure.
    """
    del as_of  # PenaltyRule carries no typed effective date until Phase 4

    sections: set[str] = set()
    by_section: dict[str, DiscrepancyType] = {}
    for d in discrepancies:
        for section in _CANDIDATE_SECTIONS.get(d.type, ()):
            sections.add(section)
            by_section.setdefault(section, d.type)

    if not sections:
        return []

    rows = await _query_best_effort(sorted(sections))

    return [
        PenaltyExposure(
            discrepancy_type=by_section.get(
                row["section_number"], DiscrepancyType.TAX_MISMATCH
            ),
            section_reference=row["section_number"],
            quantum=row.get("quantum") or "",
            trigger=row.get("trigger") or "",
            evidence_span=row["evidence_span"],
            chunk_id=row["chunk_id"],
        )
        for row in rows
    ]


async def _query_best_effort(sections: list[str]) -> list[dict]:
    try:
        return await asyncio.wait_for(
            get_neo4j_client().run_read(_PENALTY_QUERY, sections=sections),
            timeout=PENALTY_LOOKUP_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning("penalty lookup timed out; reporting findings without penalties")
        return []
    except Exception as exc:
        logger.warning("penalty lookup failed (%s); reporting without penalties", exc)
        return []
