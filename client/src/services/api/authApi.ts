const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export type AuthUser = {
  id: string
  email: string
  name: string
  bio: string | null
  profile_photo_url: string | null
  created_at: string
}

export type AuthResponse = {
  access_token: string
  token_type: 'bearer'
  user: AuthUser
}

type LoginPayload = {
  email: string
  password: string
}

type RegisterPayload = LoginPayload & {
  name: string
}

type UpdateProfilePayload = {
  name: string
  bio: string | null
}

type ChangePasswordPayload = {
  current_password: string
  new_password: string
}

async function request<T>(path: string, options: RequestInit = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
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

async function uploadRequest<T>(path: string, accessToken: string, formData: FormData) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    body: formData,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? 'Something went wrong')
  }

  return response.json() as Promise<T>
}

export const authApi = {
  login(payload: LoginPayload) {
    return request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  register(payload: RegisterPayload) {
    return request<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  refresh() {
    return request<AuthResponse>('/auth/refresh', { method: 'POST' })
  },
  me(accessToken: string) {
    return request<AuthUser>('/auth/me', {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    })
  },
  logout() {
    return request<void>('/auth/logout', { method: 'POST' })
  },
  updateProfile(accessToken: string, payload: UpdateProfilePayload) {
    return request<AuthUser>('/auth/profile', {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify(payload),
    })
  },
  changePassword(accessToken: string, payload: ChangePasswordPayload) {
    return request<void>('/auth/password', {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify(payload),
    })
  },
  uploadProfilePhoto(accessToken: string, photo: File) {
    const formData = new FormData()
    formData.append('photo', photo)
    return uploadRequest<AuthUser>('/auth/profile/photo', accessToken, formData)
  },
}
