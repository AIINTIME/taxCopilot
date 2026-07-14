"""Commits a verified GraphRuleProposal to Neo4j via idempotent MERGE.

Only ever called when proposal.evidenceVerified is True.
Never called for PENDING_REVIEW proposals.
"""

from datetime import datetime, timezone

from app.shared.graph.neo4j_client import get_neo4j_client

_MERGE_RULE = """
MERGE (s:Section {number: $section_number})
MERGE (a:AssetClass {name: $asset_class})
MERGE (s)-[:GOVERNS]->(a)
MERGE (ref:VectorChunkRef {chunk_id: $chunk_id})
  ON CREATE SET ref.document_id = $document_id
MERGE (r:RateRule {
  section_number: $section_number,
  asset_class: $asset_class,
  effective_from: $effective_from
})
  ON CREATE SET r.rate           = $rate,
               r.indexation     = $indexation,
               r.condition_text = $condition_text,
               r.selector       = $selector
MERGE (r)-[src:SOURCED_FROM]->(ref)
  ON CREATE SET src.evidence_span = $evidence_span,
               src.auto_approved  = $auto_approved,
               src.committed_at   = $committed_at
"""


async def commit_rule_to_graph(proposal) -> None:
    await get_neo4j_client().run_write(
        _MERGE_RULE,
        section_number=proposal.sectionNumber or "UNKNOWN",
        asset_class=proposal.assetClass or "UNKNOWN",
        chunk_id=proposal.sourceChunkId,
        document_id=proposal.documentId,
        effective_from=proposal.effectiveFrom or "",
        rate=proposal.rate or "",
        indexation=proposal.indexation or "",
        condition_text=proposal.conditionText or "",
        selector=proposal.selector or "",
        evidence_span=proposal.evidenceSpan or "",
        auto_approved=proposal.autoApproved,
        committed_at=datetime.now(timezone.utc).isoformat(),
    )
