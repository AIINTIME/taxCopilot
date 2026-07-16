from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from app.db import prisma


@dataclass(frozen=True)
class PermissionDefinition:
    key: str
    label: str
    category: str
    description: str


PERMISSIONS = [
    PermissionDefinition("dashboard.view", "View dashboard", "Workspace", "Open the user dashboard."),
    PermissionDefinition("chat.create", "Use chat", "Workspace", "Create tax copilot chats."),
    PermissionDefinition("deep_research.use", "Use deep research", "Workspace", "Run deep research workflows."),
    PermissionDefinition("it_act.compare", "Compare IT Acts", "Workspace", "Use IT Act comparison."),
    PermissionDefinition("analytics.view", "View analytics", "Workspace", "Open analytics dashboards."),
    PermissionDefinition("security_audit.view", "View security audit", "Workspace", "Open security and audit tools."),
    PermissionDefinition("projects.manage", "Manage projects", "Workspace", "Create and open project workspaces."),
    PermissionDefinition("admin.stats.view", "View admin overview", "Admin", "View organization admin statistics."),
    PermissionDefinition("admin.users.manage", "Manage users", "Admin", "Create, edit, deactivate, and assign roles to users."),
    PermissionDefinition("admin.roles.manage", "Manage roles", "Admin", "Create and edit roles and permissions."),
    PermissionDefinition("admin.documents.manage", "Manage documents", "Admin", "Upload and review source documents."),
    PermissionDefinition("admin.audit_logs.view", "View audit logs", "Admin", "Inspect audit activity."),
    PermissionDefinition("admin.token_usage.view", "View token usage", "Admin", "Inspect token usage reports."),
    PermissionDefinition("admin.security.view", "View admin security", "Admin", "Inspect security posture."),
    PermissionDefinition("admin.settings.manage", "Manage settings", "Admin", "Change organization settings."),
]

DEFAULT_USER_PERMISSIONS = {
    "dashboard.view",
    "chat.create",
    "deep_research.use",
    "it_act.compare",
    "projects.manage",
}

QUERY_DOMAIN_PERMISSIONS = {
    "deep-research": "deep_research.use",
    "it-act-comparison": "it_act.compare",
    "personal-tax": "chat.create",
    "corporate": "chat.create",
    "capital-gains": "chat.create",
    "notices": "chat.create",
}


async def ensure_permission_seed() -> None:
    for definition in PERMISSIONS:
        existing = await prisma.permission.find_unique(where={"key": definition.key})
        data = {
            "key": definition.key,
            "label": definition.label,
            "category": definition.category,
            "description": definition.description,
        }
        if existing is None:
            await prisma.permission.create(data=data)
        else:
            await prisma.permission.update(where={"id": existing.id}, data=data)


async def ensure_default_role(organization_id: str):
    role = await prisma.role.find_unique(
        where={"name_organizationId": {"name": "User", "organizationId": organization_id}}
    )
    if role is None:
        role = await prisma.role.create(
            data={
                "name": "User",
                "description": "Default workspace access for standard users.",
                "organizationId": organization_id,
                "isSystem": True,
            }
        )

    await set_role_permissions(role.id, DEFAULT_USER_PERMISSIONS)
    return role


async def get_permission_ids(permission_keys: set[str] | list[str]) -> list[str]:
    if not permission_keys:
        return []
    permissions = await prisma.permission.find_many(where={"key": {"in": list(permission_keys)}})
    found_keys = {permission.key for permission in permissions}
    missing = sorted(set(permission_keys) - found_keys)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown permissions: {', '.join(missing)}",
        )
    return [permission.id for permission in permissions]


async def set_role_permissions(role_id: str, permission_keys: set[str] | list[str]) -> None:
    permission_ids = await get_permission_ids(permission_keys)
    await prisma.rolepermission.delete_many(where={"roleId": role_id})
    for permission_id in permission_ids:
        await prisma.rolepermission.create(
            data={"roleId": role_id, "permissionId": permission_id}
        )


async def validate_org_roles(role_ids: list[str], organization_id: str) -> list[str]:
    deduped = list(dict.fromkeys(role_ids))
    if not deduped:
        return []
    roles = await prisma.role.find_many(
        where={"id": {"in": deduped}, "organizationId": organization_id}
    )
    if len(roles) != len(deduped):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more roles do not belong to this organization",
        )
    return deduped


async def set_user_roles(user_id: str, role_ids: list[str], organization_id: str) -> None:
    valid_role_ids = await validate_org_roles(role_ids, organization_id)
    await prisma.userrole.delete_many(where={"userId": user_id})
    for role_id in valid_role_ids:
        await prisma.userrole.create(data={"userId": user_id, "roleId": role_id})


async def get_user_permissions(user_id: str) -> set[str]:
    assignments = await prisma.userrole.find_many(
        where={"userId": user_id},
        include={"role": {"include": {"permissions": {"include": {"permission": True}}}}},
    )
    return {
        role_permission.permission.key
        for assignment in assignments
        for role_permission in assignment.role.permissions
    }


async def get_user_role_names(user_id: str) -> list[str]:
    assignments = await prisma.userrole.find_many(
        where={"userId": user_id}, include={"role": True}
    )
    return [assignment.role.name for assignment in assignments]


async def ensure_user_rbac_baseline(user) -> None:
    if not user.organizationId:
        return

    default_role = await ensure_default_role(user.organizationId)
    assignments = await prisma.userrole.find_many(
        where={"userId": user.id}, include={"role": True}
    )
    if not assignments:
        await set_user_roles(user.id, [default_role.id], user.organizationId)
        return

    assigned_default_role = any(
        assignment.role.id == default_role.id or assignment.role.name == default_role.name
        for assignment in assignments
    )
    if assigned_default_role and not await get_user_permissions(user.id):
        await set_user_roles(
            user.id,
            [assignment.role.id for assignment in assignments],
            user.organizationId,
        )


def require_permission(permission: str):
    from app.api.auth import get_current_user

    async def dependency(request: Request, user=Depends(get_current_user)):
        permissions = set(getattr(request.state, "permissions", []) or [])
        if not permissions:
            permissions = await get_user_permissions(user.id)
            request.state.permissions = sorted(permissions)
        if permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return user

    return dependency


async def require_query_permission(domain: str, user, request: Request):
    permission = QUERY_DOMAIN_PERMISSIONS.get(domain, "chat.create")
    permissions = set(getattr(request.state, "permissions", []) or [])
    if not permissions:
        permissions = await get_user_permissions(user.id)
        request.state.permissions = sorted(permissions)
    if permission not in permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to use this workspace",
        )
