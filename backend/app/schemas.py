from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class OrganizationResponse(BaseModel):
    id: str
    slug: str
    display_name: str


class AdminRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    organization_id: str


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)
    organization_id: str


class AdminResponse(BaseModel):
    id: str
    username: str
    organization_id: str
    created_at: datetime


class AdminAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin: AdminResponse


class AdminStatsResponse(BaseModel):
    total_users: int
    total_audit_logs: int
    total_provisions: int
    security_alerts: int


class AdminUserItem(BaseModel):
    id: str
    name: str
    email: str
    organization_id: str | None = None
    admin_id: str | None = None
    is_active: bool = True
    created_at: datetime
    role_ids: list[str] = []
    roles: list[str] = []
    permissions: list[str] = []


class AdminCreateUserRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role_ids: list[str] = []


class AdminUpdateUserRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None


class AdminSetUserPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class AdminSetUserActiveRequest(BaseModel):
    is_active: bool


class AdminAssignUserRolesRequest(BaseModel):
    role_ids: list[str] = []


class PermissionItem(BaseModel):
    id: str
    key: str
    label: str
    description: str | None = None
    category: str


class RoleItem(BaseModel):
    id: str
    name: str
    description: str | None = None
    is_system: bool
    permission_keys: list[str]
    user_count: int = 0
    created_at: datetime


class CreateRoleRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=240)
    permission_keys: list[str] = []


class UpdateRoleRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=240)
    permission_keys: list[str] | None = None


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    organization_id: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    organization_id: str


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    bio: str | None = None
    profile_photo_url: str | None = None
    organization_id: str | None = None
    is_active: bool = True
    roles: list[str] = []
    permissions: list[str] = []
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UpdateProfileRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    bio: str | None = Field(default=None, max_length=500)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class DocumentUploadResponse(BaseModel):
    document_id: str
    status: str  # "UPLOADED" | "SKIPPED_DUPLICATE"
    chunks_embedded: int
    rule_proposals_created: int
    auto_approved_count: int
    pending_review_count: int


class RuleProposalItem(BaseModel):
    id: str
    document_id: str
    source_chunk_id: str
    section_number: str | None
    asset_class: str | None
    rate: str | None
    evidence_span: str | None
    evidence_verified: bool
    status: str
    auto_approved: bool
    created_at: datetime
