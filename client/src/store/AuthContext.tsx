import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { authApi } from '../services/api/authApi'
import type { AuthUser } from '../services/api/authApi'
import { setAccessToken as setSharedAccessToken } from '../services/api/authToken'

type AuthContextValue = {
  user: AuthUser | null
  accessToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (email: string, password: string, organizationId: string) => Promise<void>
  register: (name: string, email: string, password: string, organizationId: string) => Promise<void>
  logout: () => Promise<void>
  updateProfile: (payload: { name: string; bio: string | null }) => Promise<void>
  uploadProfilePhoto: (photo: File) => Promise<void>
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let isMounted = true

    authApi
      .refresh()
      .then((response) => {
        if (!isMounted) return
        setUser(response.user)
        setAccessToken(response.access_token)
        setSharedAccessToken(response.access_token)
      })
      .catch(() => {
        if (!isMounted) return
        setUser(null)
        setAccessToken(null)
        setSharedAccessToken(null)
      })
      .finally(() => {
        if (isMounted) setIsLoading(false)
      })

    return () => {
      isMounted = false
    }
  }, [])

  const login = useCallback(async (email: string, password: string, organizationId: string) => {
    const response = await authApi.login({ email, password, organization_id: organizationId })
    setUser(response.user)
    setAccessToken(response.access_token)
    setSharedAccessToken(response.access_token)
  }, [])

  const register = useCallback(async (name: string, email: string, password: string, organizationId: string) => {
    const response = await authApi.register({ name, email, password, organization_id: organizationId })
    setUser(response.user)
    setAccessToken(response.access_token)
    setSharedAccessToken(response.access_token)
  }, [])

  const logout = useCallback(async () => {
    await authApi.logout().catch(() => undefined)
    setUser(null)
    setAccessToken(null)
    setSharedAccessToken(null)
  }, [])

  const updateProfile = useCallback(
    async (payload: { name: string; bio: string | null }) => {
      if (!accessToken) throw new Error('You need to log in again')
      const updatedUser = await authApi.updateProfile(accessToken, payload)
      setUser(updatedUser)
    },
    [accessToken],
  )

  const uploadProfilePhoto = useCallback(
    async (photo: File) => {
      if (!accessToken) throw new Error('You need to log in again')
      const updatedUser = await authApi.uploadProfilePhoto(accessToken, photo)
      setUser(updatedUser)
    },
    [accessToken],
  )

  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string) => {
      if (!accessToken) throw new Error('You need to log in again')
      await authApi.changePassword(accessToken, {
        current_password: currentPassword,
        new_password: newPassword,
      })
    },
    [accessToken],
  )

  const value = useMemo(
    () => ({
      user,
      accessToken,
      isAuthenticated: Boolean(user && accessToken),
      isLoading,
      login,
      register,
      logout,
      updateProfile,
      uploadProfilePhoto,
      changePassword,
    }),
    [accessToken, changePassword, isLoading, login, logout, register, updateProfile, uploadProfilePhoto, user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
