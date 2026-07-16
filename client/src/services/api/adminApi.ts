const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export type AdminUser = {
  id: string
  username: string
  organization_id: string
  created_at: string
}

export type AdminAuthResponse = {
  access_token: string
  token_type: 'bearer'
  admin: AdminUser
}

export type AdminStats = {
  total_users: number
  total_audit_logs: number
  total_provisions: number
  security_alerts: number
}

export type AdminUserItem = {
  id: string
  name: string
  email: string
  organization_id: string | null
  admin_id: string | null
  is_active: boolean
  role_ids: string[]
  roles: string[]
  permissions: string[]
  created_at: string
}

export type PermissionItem = {
  id: string
  key: string
  label: string
  description: string | null
  category: string
}

export type RoleItem = {
  id: string
  name: string
  description: string | null
  is_system: boolean
  permission_keys: string[]
  user_count: number
  created_at: string
}

export type DocumentUploadResponse = {
  document_id: string
  status: 'UPLOADED' | 'SKIPPED_DUPLICATE'
  chunks_embedded: number
  rule_proposals_created: number
  auto_approved_count: number
  pending_review_count: number
}

export type DocumentListItem = {
  id: string
  filename: string
  status: 'PROCESSING' | 'EMBEDDED' | 'FAILED'
  chunks_embedded: number
  uploaded_by: string
  created_at: string
}

async function request<T>(path: string, options: RequestInit = {}) {
  const isFormData = options.body instanceof FormData

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? 'Something went wrong')
  }

  if (response.status === 204) return undefined as T

  return response.json() as Promise<T>
}

export const adminApi = {
  login(payload: { username: string; password: string; organization_id: string }) {
    return request<AdminAuthResponse>('/admin/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  register(payload: { username: string; password: string; organization_id: string }) {
    return request<AdminAuthResponse>('/admin/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  refresh() {
    return request<AdminAuthResponse>('/admin/auth/refresh', { method: 'POST' })
  },
  me(accessToken: string) {
    return request<AdminUser>('/admin/auth/me', {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  },
  logout() {
    return request<void>('/admin/auth/logout', { method: 'POST' })
  },
  getStats(accessToken: string) {
    return request<AdminStats>('/admin/stats', {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  },
  getUsers(accessToken: string) {
    return request<AdminUserItem[]>('/admin/users', {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  },
  createUser(
    accessToken: string,
    payload: { name: string; email: string; password: string; role_ids: string[] },
  ) {
    return request<AdminUserItem>('/admin/users', {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify(payload),
    })
  },
  updateUser(
    accessToken: string,
    userId: string,
    payload: { name?: string; email?: string },
  ) {
    return request<AdminUserItem>(`/admin/users/${userId}`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify(payload),
    })
  },
  setUserPassword(accessToken: string, userId: string, password: string) {
    return request<void>(`/admin/users/${userId}/password`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ password }),
    })
  },
  setUserStatus(accessToken: string, userId: string, isActive: boolean) {
    return request<AdminUserItem>(`/admin/users/${userId}/status`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ is_active: isActive }),
    })
  },
  assignUserRoles(accessToken: string, userId: string, roleIds: string[]) {
    return request<AdminUserItem>(`/admin/users/${userId}/roles`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ role_ids: roleIds }),
    })
  },
  getPermissions(accessToken: string) {
    return request<PermissionItem[]>('/admin/permissions', {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  },
  getRoles(accessToken: string) {
    return request<RoleItem[]>('/admin/roles', {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  },
  createRole(
    accessToken: string,
    payload: { name: string; description: string | null; permission_keys: string[] },
  ) {
    return request<RoleItem>('/admin/roles', {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify(payload),
    })
  },
  updateRole(
    accessToken: string,
    roleId: string,
    payload: { name?: string; description?: string | null; permission_keys?: string[] },
  ) {
    return request<RoleItem>(`/admin/roles/${roleId}`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify(payload),
    })
  },
  deleteRole(accessToken: string, roleId: string) {
    return request<void>(`/admin/roles/${roleId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  },
  getAuditLogs(accessToken: string) {
    return request<{ id: string; userId: string | null; query: string; gateStatus: string; createdAt: string }[]>(
      '/admin/audit-logs',
      { headers: { Authorization: `Bearer ${accessToken}` } },
    )
  },
  uploadDocument(accessToken: string, file: File) {
    const formData = new FormData()
    formData.append('file', file)

    return request<DocumentUploadResponse>('/admin/documents/upload', {
      method: 'POST',
      body: formData,
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  },
  listDocuments(accessToken: string) {
    return request<DocumentListItem[]>('/admin/documents', {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
  },
}
