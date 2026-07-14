import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { adminApi } from '../services/api/adminApi'
import type { AdminUser } from '../services/api/adminApi'

type AdminAuthContextValue = {
  admin: AdminUser | null
  accessToken: string | null
  isAdminAuthenticated: boolean
  isLoading: boolean
  login: (username: string, password: string, organizationId: string) => Promise<void>
  register: (username: string, password: string, organizationId: string) => Promise<void>
  logout: () => Promise<void>
}

export const AdminAuthContext = createContext<AdminAuthContextValue | null>(null)

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [admin, setAdmin] = useState<AdminUser | null>(null)
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let isMounted = true

    adminApi
      .refresh()
      .then((response) => {
        if (!isMounted) return
        setAdmin(response.admin)
        setAccessToken(response.access_token)
      })
      .catch(() => {
        if (!isMounted) return
        setAdmin(null)
        setAccessToken(null)
      })
      .finally(() => {
        if (isMounted) setIsLoading(false)
      })

    return () => {
      isMounted = false
    }
  }, [])

  const login = useCallback(async (username: string, password: string, organizationId: string) => {
    const response = await adminApi.login({ username, password, organization_id: organizationId })
    setAdmin(response.admin)
    setAccessToken(response.access_token)
  }, [])

  const register = useCallback(async (username: string, password: string, organizationId: string) => {
    const response = await adminApi.register({ username, password, organization_id: organizationId })
    setAdmin(response.admin)
    setAccessToken(response.access_token)
  }, [])

  const logout = useCallback(async () => {
    await adminApi.logout().catch(() => undefined)
    setAdmin(null)
    setAccessToken(null)
  }, [])

  const value = useMemo(
    () => ({
      admin,
      accessToken,
      isAdminAuthenticated: Boolean(admin && accessToken),
      isLoading,
      login,
      register,
      logout,
    }),
    [admin, accessToken, isLoading, login, register, logout],
  )

  return <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>
}
