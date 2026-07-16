import {
  BarChart3,
  FileDiff,
  Gauge,
  LayoutDashboard,
  LockKeyhole,
  Menu,
  Pencil,
  Plus,
  Search,
  SearchCheck,
  Trash2,
  X,
} from 'lucide-react'
import type { FormEvent, KeyboardEvent } from 'react'
import { useMemo, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { sidebarProjects } from '../../constants/dashboard'
import { hasPermission } from '../../constants/permissions'
import { workflows } from '../../constants/workflows'
import { useAppState } from '../../store/useAppState'
import { useAuth } from '../../store/useAuth'
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
  const [editingConversationId, setEditingConversationId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const {
    conversations,
    activeConversationId,
    selectConversation,
    renameConversation,
    deleteConversation,
  } = useAppState()
  const { user } = useAuth()
  const navigate = useNavigate()
  const permissions = user?.permissions ?? []
  const visiblePrimaryNavItems = primaryNavItems.filter((item) => {
    if (item.path === '/') return hasPermission(permissions, 'dashboard.view')
    if (item.path === '/deep-research') return hasPermission(permissions, 'deep_research.use')
    if (item.path === '/it-act-comparison') return hasPermission(permissions, 'it_act.compare')
    if (item.path === '/analytics') return hasPermission(permissions, 'analytics.view')
    if (item.path === '/security-audit') return hasPermission(permissions, 'security_audit.view')
    return true
  })
  const filteredConversations = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    if (!normalizedQuery) return conversations

    return conversations.filter((conversation) => {
      const workflow = workflows.find((item) => item.id === conversation.workflowId)
      return `${conversation.title} ${workflow?.name ?? ''}`.toLowerCase().includes(normalizedQuery)
    })
  }, [conversations, query])
  const groups = groupConversations(filteredConversations).slice(0, 3)

  function openConversation(conversationId: string) {
    selectConversation(conversationId)
    const conversation = conversations.find((item) => item.id === conversationId)
    const workflow = workflows.find((item) => item.id === conversation?.workflowId) ?? workflows[0]
    navigate(workflow.path)
  }

  function startRename(conversationId: string, title: string) {
    setEditingConversationId(conversationId)
    setEditingTitle(title)
  }

  function cancelRename() {
    setEditingConversationId(null)
    setEditingTitle('')
  }

  function submitRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editingConversationId) return

    const title = editingTitle.trim()
    if (title) renameConversation(editingConversationId, title)
    cancelRename()
  }

  function handleRenameKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') cancelRename()
  }

  function removeConversation(conversationId: string) {
    deleteConversation(conversationId)
    if (conversationId === activeConversationId) navigate('/new-chat')
  }

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
        {isCollapsed ? (
          <button className="sidebar-logo-button" type="button" aria-label="Go to dashboard" onClick={() => navigate('/')}>
            <img src="/logo/logo.png" alt="" />
          </button>
        ) : (
          <IconButton label="Collapse sidebar" className="sidebar__menu" onClick={onToggle}>
            <Menu size={18} />
          </IconButton>
        )}
      </div>

      {hasPermission(permissions, 'chat.create') ? (
        <button className="new-chat" type="button" aria-label="New chat" onClick={() => navigate('/new-chat')}>
          <Plus size={18} />
          New chat
        </button>
      ) : null}

      <section className="sidebar-section">
        <h2>Workspace</h2>
        <nav className="primary-nav" aria-label="Application navigation">
          {visiblePrimaryNavItems.map((item) => {
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
        {hasPermission(permissions, 'projects.manage') ? (
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
        ) : null}
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
                {group.conversations.slice(0, 4).map((conversation) => {
                  const isEditing = editingConversationId === conversation.id

                  return (
                    <article
                      className={`history-item ${conversation.id === activeConversationId ? 'is-active' : ''}`}
                      key={conversation.id}
                    >
                      {isEditing ? (
                        <form className="history-item__rename" onSubmit={submitRename}>
                          <input
                            autoFocus
                            value={editingTitle}
                            onChange={(event) => setEditingTitle(event.target.value)}
                            onKeyDown={handleRenameKeyDown}
                            aria-label="Rename chat"
                          />
                          <button type="button" onClick={cancelRename} aria-label="Cancel rename" title="Cancel">
                            <X size={14} />
                          </button>
                        </form>
                      ) : (
                        <>
                          <button
                            className="history-item__main"
                            type="button"
                            onClick={() => openConversation(conversation.id)}
                          >
                            <span>{conversation.title}</span>
                            <small>{conversation.messages.length} messages</small>
                          </button>
                          <div className="history-item__actions" aria-label="Chat actions">
                            <button
                              type="button"
                              onClick={() => startRename(conversation.id, conversation.title)}
                              aria-label={`Rename ${conversation.title}`}
                              title="Rename"
                            >
                              <Pencil size={14} />
                            </button>
                            <button
                              type="button"
                              onClick={() => removeConversation(conversation.id)}
                              aria-label={`Delete ${conversation.title}`}
                              title="Delete"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </>
                      )}
                    </article>
                  )
                })}
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
