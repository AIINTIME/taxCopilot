from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile

from app.api.admin_auth import get_current_admin
from app.db import prisma
from app.schemas import (
    AdminStatsResponse,
    AdminUserItem,
    DocumentUploadResponse,
    RuleProposalItem,
)
from app.services.ingestion.dedup import content_hash
from app.services.ingestion.kg_graph_extraction.pipeline import process_chunk_for_graph
from app.services.ingestion.parsing.pdf_parser import chunk_document, parse_pdf
from app.services.ingestion.upsert.statutory_kg_upsert import upsert_chunk_to_statutory_kg

router = APIRouter(tags=["admin"])


@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(_admin=Depends(get_current_admin)):
    total_users = await prisma.user.count()
    total_audit_logs = await prisma.auditlog.count()
    total_provisions = await prisma.knowledgegraphprovision.count()
    return AdminStatsResponse(
        total_users=total_users,
        total_audit_logs=total_audit_logs,
        total_provisions=total_provisions,
        security_alerts=0,
    )


@router.get("/users", response_model=list[AdminUserItem])
async def get_users(_admin=Depends(get_current_admin)):
    users = await prisma.user.find_many(order={"createdAt": "desc"}, take=50)
    return [
        AdminUserItem(
            id=u.id,
            name=u.name,
            email=u.email,
            organization_id=u.organizationId,
            created_at=u.createdAt,
        )
        for u in users
    ]


@router.get("/audit-logs")
async def get_audit_logs(_admin=Depends(get_current_admin)):
    logs = await prisma.auditlog.find_many(order={"createdAt": "desc"}, take=20)
    return [
        {
            "id": log.id,
            "userId": log.userId,
            "query": log.query[:100],
            "gateStatus": log.gateStatus.value,
            "createdAt": log.createdAt.isoformat(),
        }
        for log in logs
    ]


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile,
    admin=Depends(get_current_admin),
):
    content = await file.read()
    file_hash = content_hash(content)

    # Dedup check — same bytes already ingested
    existing = await prisma.document.find_unique(where={"contentHash": file_hash})
    if existing:
        return DocumentUploadResponse(
            document_id=existing.id,
            status="SKIPPED_DUPLICATE",
            chunks_embedded=existing.chunksEmbedded,
            rule_proposals_created=0,
            auto_approved_count=0,
            pending_review_count=0,
        )

    # Save file locally (s3Path stores the local path for now)
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(exist_ok=True)
    safe_name = file.filename or "upload"
    file_path = uploads_dir / f"{file_hash}_{safe_name}"
    file_path.write_bytes(content)

    # Create Document row — status PROCESSING
    doc = await prisma.document.create(
        data={
            "filename": safe_name,
            "contentHash": file_hash,
            "s3Path": str(file_path),
            "organizationId": admin.organizationId,
            "uploadedByAdminId": admin.id,
            "status": "PROCESSING",
        }
    )

    try:
        text = parse_pdf(content)
        chunks = chunk_document(text)

        proposals = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc.id}:chunk:{i}"

            # Vector path — embed + upsert to Pinecone statutory-kg
            await upsert_chunk_to_statutory_kg(
                chunk_id=chunk_id,
                chunk_text=chunk,
                document_id=doc.id,
                source_id=file_hash,
                tier=10,
            )

            # Graph path — extract rule + (optionally) commit to Neo4j
            proposal = await process_chunk_for_graph(
                chunk_text=chunk,
                chunk_id=chunk_id,
                document_id=doc.id,
                org_id=admin.organizationId,
            )
            if proposal:
                proposals.append(proposal)

        await prisma.document.update(
            where={"id": doc.id},
            data={"status": "EMBEDDED", "chunksEmbedded": len(chunks)},
        )

        auto_approved = sum(1 for p in proposals if p.autoApproved)
        pending = sum(1 for p in proposals if p.status == "PENDING_REVIEW")

        return DocumentUploadResponse(
            document_id=doc.id,
            status="UPLOADED",
            chunks_embedded=len(chunks),
            rule_proposals_created=len(proposals),
            auto_approved_count=auto_approved,
            pending_review_count=pending,
        )

    except Exception:
        await prisma.document.update(
            where={"id": doc.id}, data={"status": "FAILED"}
        )
        raise


@router.get("/rule-proposals", response_model=list[RuleProposalItem])
async def list_rule_proposals(
    status: str | None = None,
    admin=Depends(get_current_admin),
):
    where: dict = {"organizationId": admin.organizationId}
    if status:
        where["status"] = status

    proposals = await prisma.graphruleproposal.find_many(
        where=where, order={"createdAt": "desc"}, take=50
    )
    return [
        RuleProposalItem(
            id=p.id,
            document_id=p.documentId,
            source_chunk_id=p.sourceChunkId,
            section_number=p.sectionNumber,
            asset_class=p.assetClass,
            rate=p.rate,
            evidence_span=p.evidenceSpan,
            evidence_verified=p.evidenceVerified,
            status=p.status.value,
            auto_approved=p.autoApproved,
            created_at=p.createdAt,
        )
        for p in proposals
    ]
