import { AlertTriangle, Bell, CheckCircle2, FileText, LogOut, Menu, Moon, Sun, UserCog, UserRound } from 'lucide-react'
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { workflows } from '../../constants/workflows'
import { useAppState } from '../../store/useAppState'
import { useAuth } from '../../store/useAuth'
import { IconButton } from '../common/IconButton'

function getHeaderTitle(pathname: string) {
  const workflow = workflows.find((item) => item.path === pathname)
  if (workflow) return workflow.name
  if (pathname === '/projects/new') return 'New Project'
  if (pathname.startsWith('/projects/')) return 'Project'
  if (pathname === '/new-chat') return 'New Chat'
  if (pathname === '/deep-research') return 'Deep Research'
  if (pathname === '/it-act-comparison') return 'IT Act comparison'
  if (pathname === '/analytics') return 'Analytics'
  if (pathname === '/security-audit') return 'Security and Audit'
  if (pathname === '/profile') return 'Profile'
  return 'Dashboard'
}

type TopHeaderProps = {
  isSidebarCollapsed: boolean
  onToggleSidebar: () => void
}

const mockNotifications = [
  {
    id: 'notice-review',
    title: 'Notice review completed',
    detail: 'Draft response for AY 2024-25 is ready to review.',
    time: '4m ago',
    tone: 'success',
    icon: CheckCircle2,
  },
  {
    id: 'risk-flag',
    title: 'Potential mismatch found',
    detail: 'AIS income differs from the uploaded Form 26AS by Rs. 18,420.',
    time: '28m ago',
    tone: 'warning',
    icon: AlertTriangle,
  },
  {
    id: 'project-summary',
    title: 'Project summary updated',
    detail: 'Corporate tax workspace received 3 new extracted clauses.',
    time: '1h ago',
    tone: 'info',
    icon: FileText,
  },
]

export function TopHeader({ isSidebarCollapsed, onToggleSidebar }: TopHeaderProps) {
  const [profileOpen, setProfileOpen] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { settings, toggleTheme } = useAppState()
  const { user, logout } = useAuth()
  const title = getHeaderTitle(pathname)
  const initials =
    user?.name
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('') || 'U'

  return (
    <header className="top-header">
      <div>
        <div className="top-header__title-row">
          {isSidebarCollapsed ? (
            <IconButton label="Expand sidebar" className="header-menu-button" onClick={onToggleSidebar}>
              <Menu size={18} />
            </IconButton>
          ) : null}
          <div>
            <span>Workspace</span>
            <strong>{title}</strong>
          </div>
        </div>
      </div>
      <div className="top-header__actions">
        <div className="notification-menu">
          <IconButton
            label="Notifications"
            className="notification-button"
            aria-expanded={notificationsOpen}
            onClick={() => {
              setNotificationsOpen((value) => !value)
              setProfileOpen(false)
            }}
          >
            <Bell size={18} />
            <span aria-hidden="true" />
          </IconButton>
          {notificationsOpen ? (
            <div className="notification-dropdown glass-panel">
              <header>
                <div>
                  <strong>Notifications</strong>
                  <span>{mockNotifications.length} unread updates</span>
                </div>
                <button type="button">Mark read</button>
              </header>
              <div className="notification-list">
                {mockNotifications.map((notification) => {
                  const NotificationIcon = notification.icon

                  return (
                    <button className="notification-item" type="button" key={notification.id}>
                      <span className={`notification-item__icon is-${notification.tone}`}>
                        <NotificationIcon size={16} />
                      </span>
                      <span>
                        <strong>{notification.title}</strong>
                        <small>{notification.detail}</small>
                      </span>
                      <time>{notification.time}</time>
                    </button>
                  )
                })}
              </div>
            </div>
          ) : null}
        </div>
        <IconButton label="Toggle theme" onClick={toggleTheme}>
          {settings.darkMode ? <Sun size={18} /> : <Moon size={18} />}
        </IconButton>
        <div className="profile-menu">
          <button
            type="button"
            className="profile-trigger"
            onClick={() => {
              setProfileOpen((value) => !value)
              setNotificationsOpen(false)
            }}
          >
            <span>{initials}</span>
            <UserRound size={17} />
          </button>
          {profileOpen ? (
            <div className="profile-dropdown glass-panel">
              <button
                type="button"
                onClick={() => {
                  setProfileOpen(false)
                  navigate('/profile')
                }}
              >
                <UserCog size={16} />
                Profile management
              </button>
              <button type="button" onClick={logout}>
                <LogOut size={16} />
                Logout
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  )
}
