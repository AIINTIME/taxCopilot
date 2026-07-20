from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.api.admin_auth import get_current_admin
from app.core.rbac import (
    ensure_default_role,
    set_role_permissions,
    set_user_roles,
    validate_org_roles,
)
from app.core.security import hash_password
from app.db import prisma
from app.schemas import (
    AdminAssignUserRolesRequest,
    AdminCreateUserRequest,
    AdminSetUserActiveRequest,
    AdminSetUserPasswordRequest,
    AdminStatsResponse,
    AdminUpdateUserRequest,
    AdminUserItem,
    CreateRoleRequest,
    DocumentListItem,
    DocumentUploadResponse,
    PermissionItem,
    RoleItem,
    RuleProposalItem,
    UpdateRoleRequest,
)
from app.services.ingestion.dedup import content_hash
from app.services.ingestion.kg_graph_extraction.pipeline import process_chunk_for_graph
from app.services.ingestion.parsing.docx_parser import parse_docx
from app.services.ingestion.parsing.pdf_parser import chunk_document, parse_pdf
from app.services.ingestion.parsing.text_parser import parse_text
from app.services.ingestion.upsert.statutory_kg_upsert import upsert_chunk_to_statutory_kg

router = APIRouter(tags=["admin"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

PARSERS = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".txt": parse_text,
    ".md": parse_text,
}


async def serialize_admin_user(user) -> AdminUserItem:
    assignments = await prisma.userrole.find_many(
        where={"userId": user.id},
        include={"role": {"include": {"permissions": {"include": {"permission": True}}}}},
    )
    permission_keys = sorted(
        {
            role_permission.permission.key
            for assignment in assignments
            for role_permission in assignment.role.permissions
        }
    )
    return AdminUserItem(
        id=user.id,
        name=user.name,
        email=user.email,
        organization_id=user.organizationId,
        admin_id=user.adminId,
        is_active=user.isActive,
        created_at=user.createdAt,
        role_ids=[assignment.role.id for assignment in assignments],
        roles=[assignment.role.name for assignment in assignments],
        permissions=permission_keys,
    )


async def serialize_role(role) -> RoleItem:
    role_permissions = await prisma.rolepermission.find_many(
        where={"roleId": role.id}, include={"permission": True}
    )
    user_count = await prisma.userrole.count(where={"roleId": role.id})
    return RoleItem(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system=role.isSystem,
        permission_keys=sorted(
            role_permission.permission.key for role_permission in role_permissions
        ),
        user_count=user_count,
        created_at=role.createdAt,
    )


async def get_user_for_admin(user_id: str, admin):
    user = await prisma.user.find_first(
        where={"id": user_id, "organizationId": admin.organizationId}
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(admin=Depends(get_current_admin)):
    total_users = await prisma.user.count(
        where={"organizationId": admin.organizationId}
    )
    total_audit_logs = await prisma.auditlog.count()
    total_provisions = await prisma.knowledgegraphprovision.count()
    return AdminStatsResponse(
        total_users=total_users,
        total_audit_logs=total_audit_logs,
        total_provisions=total_provisions,
        security_alerts=0,
    )


@router.get("/users", response_model=list[AdminUserItem])
async def get_users(admin=Depends(get_current_admin)):
    users = await prisma.user.find_many(
        where={"organizationId": admin.organizationId},
        order={"createdAt": "desc"},
        take=50,
    )
    return [await serialize_admin_user(u) for u in users]


@router.post(
    "/users", response_model=AdminUserItem, status_code=status.HTTP_201_CREATED
)
async def create_user(
    payload: AdminCreateUserRequest, admin=Depends(get_current_admin)
):
    normalized_email = payload.email.lower().strip()
    existing_user = await prisma.user.find_unique(where={"email": normalized_email})
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
        )

    user = await prisma.user.create(
        data={
            "email": normalized_email,
            "name": payload.name.strip(),
            "passwordHash": hash_password(payload.password),
            "organizationId": admin.organizationId,
            "adminId": admin.id,
        }
    )
    if payload.role_ids:
        role_ids = await validate_org_roles(payload.role_ids, admin.organizationId)
    else:
        role_ids = [(await ensure_default_role(admin.organizationId)).id]
    await set_user_roles(user.id, role_ids, admin.organizationId)
    return await serialize_admin_user(user)


@router.patch("/users/{user_id}", response_model=AdminUserItem)
async def update_user(
    user_id: str, payload: AdminUpdateUserRequest, admin=Depends(get_current_admin)
):
    await get_user_for_admin(user_id, admin)
    data: dict[str, str] = {}

    if payload.name is not None:
        data["name"] = payload.name.strip()

    if payload.email is not None:
        normalized_email = payload.email.lower().strip()
        existing_user = await prisma.user.find_unique(where={"email": normalized_email})
        if existing_user is not None and existing_user.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            )
        data["email"] = normalized_email

    if not data:
        return await serialize_admin_user(await get_user_for_admin(user_id, admin))

    user = await prisma.user.update(where={"id": user_id}, data=data)
    return await serialize_admin_user(user)


@router.patch("/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def set_user_password(
    user_id: str,
    payload: AdminSetUserPasswordRequest,
    admin=Depends(get_current_admin),
):
    await get_user_for_admin(user_id, admin)
    await prisma.user.update(
        where={"id": user_id},
        data={"passwordHash": hash_password(payload.password)},
    )


@router.patch("/users/{user_id}/status", response_model=AdminUserItem)
async def set_user_status(
    user_id: str,
    payload: AdminSetUserActiveRequest,
    admin=Depends(get_current_admin),
):
    await get_user_for_admin(user_id, admin)
    user = await prisma.user.update(
        where={"id": user_id},
        data={"isActive": payload.is_active},
    )
    return await serialize_admin_user(user)


@router.patch("/users/{user_id}/roles", response_model=AdminUserItem)
async def assign_user_roles(
    user_id: str,
    payload: AdminAssignUserRolesRequest,
    admin=Depends(get_current_admin),
):
    user = await get_user_for_admin(user_id, admin)
    await set_user_roles(user.id, payload.role_ids, admin.organizationId)
    return await serialize_admin_user(user)


@router.get("/permissions", response_model=list[PermissionItem])
async def get_permissions(admin=Depends(get_current_admin)):
    permissions = await prisma.permission.find_many(order={"category": "asc"})
    return [
        PermissionItem(
            id=permission.id,
            key=permission.key,
            label=permission.label,
            description=permission.description,
            category=permission.category,
        )
        for permission in permissions
    ]


@router.get("/roles", response_model=list[RoleItem])
async def get_roles(admin=Depends(get_current_admin)):
    roles = await prisma.role.find_many(
        where={"organizationId": admin.organizationId}, order={"createdAt": "asc"}
    )
    return [await serialize_role(role) for role in roles]


@router.post("/roles", response_model=RoleItem, status_code=status.HTTP_201_CREATED)
async def create_role(payload: CreateRoleRequest, admin=Depends(get_current_admin)):
    name = payload.name.strip()
    existing = await prisma.role.find_unique(
        where={"name_organizationId": {"name": name, "organizationId": admin.organizationId}}
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role name already exists in this organization",
        )

    role = await prisma.role.create(
        data={
            "name": name,
            "description": payload.description.strip() if payload.description else None,
            "organizationId": admin.organizationId,
        }
    )
    await set_role_permissions(role.id, payload.permission_keys)
    return await serialize_role(role)


@router.patch("/roles/{role_id}", response_model=RoleItem)
async def update_role(
    role_id: str, payload: UpdateRoleRequest, admin=Depends(get_current_admin)
):
    role = await prisma.role.find_first(
        where={"id": role_id, "organizationId": admin.organizationId}
    )
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    data: dict[str, str | None] = {}
    if payload.name is not None:
        name = payload.name.strip()
        existing = await prisma.role.find_unique(
            where={"name_organizationId": {"name": name, "organizationId": admin.organizationId}}
        )
        if existing is not None and existing.id != role.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Role name already exists in this organization",
            )
        data["name"] = name

    if payload.description is not None:
        data["description"] = payload.description.strip() or None

    if data:
        role = await prisma.role.update(where={"id": role.id}, data=data)

    if payload.permission_keys is not None:
        await set_role_permissions(role.id, payload.permission_keys)

    return await serialize_role(role)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(role_id: str, admin=Depends(get_current_admin)):
    role = await prisma.role.find_first(
        where={"id": role_id, "organizationId": admin.organizationId}
    )
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.isSystem:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System roles cannot be deleted",
        )
    await prisma.role.delete(where={"id": role.id})


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
    safe_name = file.filename or "upload"
    extension = Path(safe_name).suffix.lower()
    parser = PARSERS.get(extension)
    if parser is None:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {extension or 'unknown'}")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 50MB limit")

    file_hash = content_hash(content)

    # Dedup check — same bytes already successfully ingested
    existing = await prisma.document.find_unique(where={"contentHash": file_hash})
    if existing and existing.status == "EMBEDDED":
        return DocumentUploadResponse(
            document_id=existing.id,
            status="SKIPPED_DUPLICATE",
            chunks_embedded=existing.chunksEmbedded,
            rule_proposals_created=0,
            auto_approved_count=0,
            pending_review_count=0,
        )
    if existing:
        # A prior attempt with these exact bytes never finished (FAILED/stuck
        # PROCESSING) — clear it so this upload can retry cleanly instead of
        # being silently skipped forever.
        await prisma.document.delete(where={"id": existing.id})

    # Save file locally (s3Path stores the local path for now)
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(exist_ok=True)
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
        text = parser(content)
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

            # Graph path — extract rule + (optionally) commit to Neo4j.
            # Isolated from the vector path: rule extraction depends on the
            # LLM provider wiring (app/services/rag/llm_client.py), which is
            # still an unfinished stub. A failure here must not take down the
            # vector ingestion that already succeeded for this chunk.
            try:
                proposal = await process_chunk_for_graph(
                    chunk_text=chunk,
                    chunk_id=chunk_id,
                    document_id=doc.id,
                    org_id=admin.organizationId,
                )
                if proposal:
                    proposals.append(proposal)
            except NotImplementedError:
                pass

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


@router.get("/documents", response_model=list[DocumentListItem])
async def list_documents(admin=Depends(get_current_admin)):
    documents = await prisma.document.find_many(
        where={"organizationId": admin.organizationId},
        include={"uploadedByAdmin": True},
        order={"createdAt": "desc"},
        take=50,
    )
    return [
        DocumentListItem(
            id=d.id,
            filename=d.filename,
            status=d.status.value,
            chunks_embedded=d.chunksEmbedded,
            uploaded_by=d.uploadedByAdmin.username if d.uploadedByAdmin else "unknown",
            created_at=d.createdAt,
        )
        for d in documents
    ]


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
