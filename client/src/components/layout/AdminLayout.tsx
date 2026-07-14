import {
  BarChart3,
  Bell,
  FileText,
  LayoutDashboard,
  LogOut,
  Moon,
  Settings,
  Shield,
  ShieldCheck,
  Sun,
  Users,
  Zap,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAdminAuth } from '../../store/useAdminAuth'

const navItems = [
  { label: 'Overview', path: '/admin', icon: LayoutDashboard, end: true },
  { label: 'Documents', path: '/admin/documents', icon: FileText },
  { label: 'Users', path: '/admin/users', icon: Users },
  { label: 'Roles & Permissions', path: '/admin/roles', icon: ShieldCheck },
  { label: 'Audit Logs', path: '/admin/audit-logs', icon: FileText },
  { label: 'Token Usage', path: '/admin/token-usage', icon: Zap },
  { label: 'Security', path: '/admin/security', icon: Shield },
  { label: 'Settings', path: '/admin/settings', icon: Settings },
]

const ADMIN_THEME_KEY = 'taxai-admin-theme'

export function AdminLayout() {
  const { admin, logout } = useAdminAuth()
  const navigate = useNavigate()
  const [isDark, setIsDark] = useState(() => {
    return (localStorage.getItem(ADMIN_THEME_KEY) ?? 'dark') === 'dark'
  })

  useEffect(() => {
    const prev = document.documentElement.dataset.theme
    document.documentElement.dataset.theme = isDark ? 'dark' : 'light'
    return () => {
      document.documentElement.dataset.theme = prev ?? 'light'
    }
  }, [isDark])

  function toggleTheme() {
    setIsDark((d) => {
      const next = !d
      localStorage.setItem(ADMIN_THEME_KEY, next ? 'dark' : 'light')
      return next
    })
  }

  async function handleLogout() {
    await logout()
    navigate('/login?tab=admin', { replace: true })
  }

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-sidebar__brand">
          <div className="admin-brand-mark">
            <img src="/logo/logo.png" alt="" />
          </div>
          <div>
            <strong>TaxAI</strong>
            <span>Admin Console</span>
          </div>
        </div>

        <nav className="admin-nav" aria-label="Admin navigation">
          {navItems.map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.label}
                to={item.path}
                end={item.end}
                className={({ isActive }) => `admin-nav__item ${isActive ? 'is-active' : ''}`}
              >
                <Icon size={17} />
                <span>{item.label}</span>
              </NavLink>
            )
          })}
        </nav>

        <div className="admin-sidebar__footer">
          <div className="admin-sidebar__user">
            <div className="admin-avatar">{admin?.username?.[0]?.toUpperCase() ?? 'A'}</div>
            <div>
              <strong>{admin?.username}</strong>
              <span>Super Admin</span>
            </div>
          </div>
          <button
            type="button"
            className="admin-logout"
            onClick={handleLogout}
            aria-label="Logout"
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      <div className="admin-workspace">
        <header className="admin-header">
          <div>
            <h1>Admin Console</h1>
            <p>Manage documents, access, audit activity, and AI usage.</p>
          </div>
          <div className="admin-header__actions">
            <button
              type="button"
              className="admin-icon-btn"
              onClick={toggleTheme}
              aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
              title={isDark ? 'Light mode' : 'Dark mode'}
            >
              {isDark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button type="button" className="admin-icon-btn" aria-label="Notifications">
              <Bell size={18} />
            </button>
            <div className="admin-avatar admin-avatar--sm">
              {admin?.username?.[0]?.toUpperCase() ?? 'A'}
            </div>
          </div>
        </header>

        <main className="admin-main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
