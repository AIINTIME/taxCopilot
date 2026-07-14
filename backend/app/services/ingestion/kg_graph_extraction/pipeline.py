"""Graph extraction pipeline for a single document chunk.

GRAPH_AUTO_APPROVE controls whether evidence-verified proposals are committed
to Neo4j immediately. When True (default), a proposal that passes the
evidence-span check is auto-committed. When False, every proposal lands in
PENDING_REVIEW for human inspection first.

This flag lives ONLY here — do not replicate it elsewhere.
"""

from datetime import datetime, timezone

from app.db import prisma
from app.services.ingestion.kg_graph_extraction.graph_writer import commit_rule_to_graph
from app.services.ingestion.kg_graph_extraction.rule_proposal import (
    propose_rule_from_chunk,
    verify_evidence_span,
)

GRAPH_AUTO_APPROVE: bool = True


async def process_chunk_for_graph(
    chunk_text: str,
    chunk_id: str,
    document_id: str,
    org_id: str,
):
    extraction = await propose_rule_from_chunk(chunk_text, chunk_id)
    if extraction is None:
        return None  # NO_RULE — no DB row created, no graph write

    evidence_verified = verify_evidence_span(extraction.get("evidence_span"), chunk_text)
    auto_approved = evidence_verified and GRAPH_AUTO_APPROVE
    proposal_status = "AUTO_APPROVED" if auto_approved else "PENDING_REVIEW"
    committed_at = datetime.now(timezone.utc) if auto_approved else None

    proposal = await prisma.graphruleproposal.create(
        data={
            "documentId": document_id,
            "sourceChunkId": chunk_id,
            "sourceChunkText": chunk_text,
            "sectionNumber": extraction.get("section_number"),
            "assetClass": extraction.get("asset_class"),
            "rate": extraction.get("rate"),
            "indexation": extraction.get("indexation"),
            "conditionText": extraction.get("condition_text"),
            "effectiveFrom": extraction.get("effective_from"),
            "selector": extraction.get("selector"),
            "evidenceSpan": extraction.get("evidence_span"),
            "evidenceVerified": evidence_verified,
            "status": proposal_status,
            "autoApproved": auto_approved,
            "committedToGraphAt": committed_at,
            "organizationId": org_id,
        }
    )

    if auto_approved:
        await commit_rule_to_graph(proposal)

    return proposal
