import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { routePermissions } from '../../constants/permissions'
import { useAuth } from '../../store/useAuth'

export function ProtectedRoute() {
  const { isAuthenticated, isLoading, user } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="auth-loading">
        <div />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  const requiredPermission = location.pathname.startsWith('/projects/')
    ? 'projects.manage'
    : routePermissions[location.pathname]
  if (requiredPermission && !user?.permissions.includes(requiredPermission)) {
    const fallbackPath = Object.entries(routePermissions).find(([, permission]) => (
      user?.permissions.includes(permission)
    ))?.[0] ?? '/profile'
    return <Navigate to={fallbackPath} replace />
  }

  return <Outlet />
}
