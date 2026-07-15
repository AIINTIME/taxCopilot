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

// ── Token store ───────────────────────────────────────────────────────────
// Authenticated methods read the token from here instead of taking it as a
// parameter, so a silent refresh triggered deep inside request() (on a 401)
// is immediately usable by the next call without every caller re-plumbing it.
let currentAccessToken: string | null = null
let tokenListener: ((token: string | null) => void) | null = null

function setAccessToken(token: string | null) {
  currentAccessToken = token
  tokenListener?.(token)
}

function onTokenChange(listener: (token: string | null) => void) {
  tokenListener = listener
}

function authHeaders(): Record<string, string> {
  return currentAccessToken ? { Authorization: `Bearer ${currentAccessToken}` } : {}
}

async function request<T>(path: string, options: RequestInit = {}, isRetry = false): Promise<T> {
  const isFormData = options.body instanceof FormData

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
    },
  })

  if (response.status === 401 && !isRetry && path !== '/admin/auth/refresh') {
    try {
      const refreshed = await request<AdminAuthResponse>('/admin/auth/refresh', { method: 'POST' }, true)
      setAccessToken(refreshed.access_token)
      return request<T>(path, { ...options, headers: { ...options.headers, ...authHeaders() } }, true)
    } catch {
      setAccessToken(null)
      // Fall through to the original 401 handling below.
    }
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? 'Something went wrong')
  }

  if (response.status === 204) return undefined as T

  return response.json() as Promise<T>
}

export const adminApi = {
  onTokenChange,
  async login(payload: { username: string; password: string; organization_id: string }) {
    const response = await request<AdminAuthResponse>('/admin/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    setAccessToken(response.access_token)
    return response
  },
  async register(payload: { username: string; password: string; organization_id: string }) {
    const response = await request<AdminAuthResponse>('/admin/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    setAccessToken(response.access_token)
    return response
  },
  async refresh() {
    const response = await request<AdminAuthResponse>('/admin/auth/refresh', { method: 'POST' })
    setAccessToken(response.access_token)
    return response
  },
  me() {
    return request<AdminUser>('/admin/auth/me', { headers: authHeaders() })
  },
  async logout() {
    await request<void>('/admin/auth/logout', { method: 'POST' })
    setAccessToken(null)
  },
  getStats() {
    return request<AdminStats>('/admin/stats', { headers: authHeaders() })
  },
  getUsers() {
    return request<AdminUserItem[]>('/admin/users', { headers: authHeaders() })
  },
  getAuditLogs() {
    return request<{ id: string; userId: string | null; query: string; gateStatus: string; createdAt: string }[]>(
      '/admin/audit-logs',
      { headers: authHeaders() },
    )
  },
  uploadDocument(file: File) {
    const formData = new FormData()
    formData.append('file', file)

    return request<DocumentUploadResponse>('/admin/documents/upload', {
      method: 'POST',
      body: formData,
      headers: authHeaders(),
    })
  },
  listDocuments() {
    return request<DocumentListItem[]>('/admin/documents', { headers: authHeaders() })
  },
}
