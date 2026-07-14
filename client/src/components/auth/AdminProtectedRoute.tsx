import { Navigate, Outlet } from 'react-router-dom'
import { useAdminAuth } from '../../store/useAdminAuth'

export function AdminProtectedRoute() {
  const { isAdminAuthenticated, isLoading } = useAdminAuth()

  if (isLoading) {
    return (
      <div className="auth-loading">
        <div />
      </div>
    )
  }

  if (!isAdminAuthenticated) {
    return <Navigate to="/login?tab=admin" replace />
  }

  return <Outlet />
}
