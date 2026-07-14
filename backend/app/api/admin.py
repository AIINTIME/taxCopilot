from fastapi import APIRouter, Depends

from app.api.admin_auth import get_current_admin
from app.db import prisma
from app.schemas import AdminStatsResponse, AdminUserItem

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
        AdminUserItem(id=u.id, name=u.name, email=u.email, organization_id=u.organizationId, created_at=u.createdAt)
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
