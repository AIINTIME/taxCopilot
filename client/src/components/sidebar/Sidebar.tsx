import {
  BarChart3,
  FileDiff,
  Gauge,
  LayoutDashboard,
  LockKeyhole,
  Menu,
  Plus,
  Search,
  SearchCheck,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { sidebarProjects } from '../../constants/dashboard'
import { workflows } from '../../constants/workflows'
import { useAppState } from '../../store/useAppState'
import { groupConversations } from '../../utils/date'
import { IconButton } from '../common/IconButton'

const primaryNavItems = [
  { label: 'Dashboard', path: '/', icon: LayoutDashboard },
  { label: 'Deep Research', path: '/deep-research', icon: SearchCheck },
  { label: 'IT Act comparison', path: '/it-act-comparison', icon: FileDiff },
  { label: 'Analytics', path: '/analytics', icon: BarChart3 },
  { label: 'Security and Audit', path: '/security-audit', icon: LockKeyhole },
]

type SidebarProps = {
  isCollapsed: boolean
  onToggle: () => void
}

export function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
  const [query, setQuery] = useState('')
  const { conversations, activeConversationId, selectConversation } = useAppState()
  const navigate = useNavigate()
  const filteredConversations = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    if (!normalizedQuery) return conversations

    return conversations.filter((conversation) => {
      const workflow = workflows.find((item) => item.id === conversation.workflowId)
      return `${conversation.title} ${workflow?.name ?? ''}`.toLowerCase().includes(normalizedQuery)
    })
  }, [conversations, query])
  const groups = groupConversations(filteredConversations).slice(0, 3)

  return (
    <aside className="sidebar" aria-label="Primary sidebar" data-collapsed={isCollapsed}>
      <div className="sidebar__top">
        <div className="brand">
          <div className="brand__mark">
            <img src="/logo/logo.png" alt="" />
          </div>
          <div>
            <strong>TaxAI</strong>
            <span>Copilot</span>
          </div>
        </div>
        <IconButton label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'} className="sidebar__menu" onClick={onToggle}>
          <Menu size={18} />
        </IconButton>
      </div>

      <button className="new-chat" type="button" aria-label="New chat" onClick={() => navigate('/new-chat')}>
        <Plus size={18} />
        New chat
      </button>

      <section className="sidebar-section">
        <h2>Workspace</h2>
        <nav className="primary-nav" aria-label="Application navigation">
          {primaryNavItems.map((item) => {
            const Icon = item.icon

            return (
              <NavLink
                key={item.label}
                to={item.path}
                title={item.label}
                className={({ isActive }) => `primary-nav__item ${isActive ? 'is-active' : ''}`}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </NavLink>
            )
          })}
        </nav>
      </section>

      <section className="sidebar-section">
        <div className="sidebar-section__title">
          <h2>Projects</h2>
          <Gauge size={14} />
        </div>
        <div className="project-list">
          <button type="button" className="project-item project-item--new" onClick={() => navigate('/projects/new')}>
            <span>New project</span>
            <small>Create knowledge space</small>
          </button>
          {sidebarProjects.map((project) => (
            <button
              key={project.id}
              type="button"
              className="project-item"
              onClick={() => navigate(`/projects/${project.id}`)}
            >
              <span>{project.name}</span>
              <small>{project.detail}</small>
            </button>
          ))}
        </div>
      </section>

      <section className="sidebar-section recent-chats">
        <h2>Recent Chats</h2>
        <label className="search-box">
          <Search size={16} />
          <input
            type="search"
            placeholder="Search chats"
            aria-label="Search recent chats"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>

        <div className="conversation-history">
          {groups.length > 0 ? (
            groups.map((group) => (
              <div key={group.label}>
                <h3>{group.label}</h3>
                {group.conversations.slice(0, 4).map((conversation) => (
                  <button
                    className={`history-item ${conversation.id === activeConversationId ? 'is-active' : ''}`}
                    key={conversation.id}
                    type="button"
                    onClick={() => {
                      selectConversation(conversation.id)
                      const workflow = workflows.find((item) => item.id === conversation.workflowId) ?? workflows[0]
                      navigate(workflow.path)
                    }}
                  >
                    <span>{conversation.title}</span>
                    <small>{conversation.messages.length} messages</small>
                  </button>
                ))}
              </div>
            ))
          ) : (
            <p className="sidebar-empty">No recent chats yet</p>
          )}
        </div>
      </section>
    </aside>
  )
}
