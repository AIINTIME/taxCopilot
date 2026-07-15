import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  FileText,
  FileUp,
  ShieldCheck,
  Upload,
  UserCheck,
  Users,
  Zap,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { adminApi } from '../services/api/adminApi'
import type { AdminStats, AdminUserItem } from '../services/api/adminApi'
import { useAdminAuth } from '../store/useAdminAuth'

const mockRecentDocuments = [
  { id: 'doc-1', name: 'Finance Act 2025 notes.pdf', type: 'PDF', updated: 'Today' },
  { id: 'doc-2', name: 'Capital gains circular digest.docx', type: 'DOCX', updated: 'Yesterday' },
  { id: 'doc-3', name: 'Depreciation rates reference.md', type: 'MD', updated: '12 Jul' },
]

const mockDocumentCount = 24

export function AdminDashboardPage() {
  const { accessToken } = useAdminAuth()
  const navigate = useNavigate()
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [users, setUsers] = useState<AdminUserItem[]>([])
  const [auditLogs, setAuditLogs] = useState<
    { id: string; userId: string | null; query: string; gateStatus: string; createdAt: string }[]
  >([])
  const [isDraggingDocument, setIsDraggingDocument] = useState(false)
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([])

  useEffect(() => {
    if (!accessToken) return

    adminApi.getStats(accessToken).then(setStats).catch(() => undefined)
    adminApi.getUsers(accessToken).then(setUsers).catch(() => undefined)
    adminApi.getAuditLogs(accessToken).then(setAuditLogs).catch(() => undefined)
  }, [accessToken])

  const statCards = [
    {
      label: 'Total Documents',
      value: stats ? String(stats.total_provisions) : '—',
      icon: FileText,
      trend: 'Knowledge provisions',
      color: '#2563eb',
    },
    {
      label: 'Active Users',
      value: stats ? String(stats.total_users) : '—',
      icon: Users,
      trend: 'Registered accounts',
      color: '#14b8a6',
    },
    {
      label: 'Token Usage',
      value: stats ? `${stats.total_audit_logs} queries` : '—',
      icon: Zap,
      trend: 'Total AI queries run',
      color: '#f59e0b',
    },
    {
      label: 'Security Alerts',
      value: stats ? String(stats.security_alerts) : '—',
      icon: AlertTriangle,
      trend: 'No active threats',
      color: stats?.security_alerts ? '#ef4444' : '#22c55e',
    },
  ]

  function gateStatusBadge(status: string) {
    const map: Record<string, string> = {
      VERIFIED: 'admin-badge--green',
      PARTIAL: 'admin-badge--yellow',
      FLAGGED: 'admin-badge--red',
    }
    return `admin-badge ${map[status] ?? ''}`
  }

  function updateSelectedDocuments(files: FileList | null) {
    if (!files?.length) return
    setSelectedDocuments(Array.from(files).map((file) => file.name).slice(0, 3))
  }

  function handleDocumentDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setIsDraggingDocument(true)
  }

  function handleDocumentDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setIsDraggingDocument(false)
    updateSelectedDocuments(event.dataTransfer.files)
  }

  function handleDocumentPick(event: ChangeEvent<HTMLInputElement>) {
    updateSelectedDocuments(event.target.files)
  }

  return (
    <div className="admin-dashboard">
      <div className="admin-stats-row">
        {statCards.map((card) => {
          const Icon = card.icon
          return (
            <div key={card.label} className="admin-stat-card">
              <div className="admin-stat-card__icon" style={{ color: card.color }}>
                <Icon size={22} />
              </div>
              <div>
                <p className="admin-stat-card__label">{card.label}</p>
                <strong className="admin-stat-card__value">{card.value}</strong>
                <span className="admin-stat-card__trend">{card.trend}</span>
              </div>
            </div>
          )
        })}
      </div>

      <div className="admin-grid admin-grid--2col">
        <div className="admin-card">
          <div className="admin-card__header">
            <h2>
              <FileText size={16} />
              Document Management
            </h2>
            <span className="admin-badge admin-badge--green">{mockDocumentCount} documents</span>
          </div>
          <label
            className={`admin-upload-area ${isDraggingDocument ? 'is-dragging' : ''}`}
            onDragOver={handleDocumentDragOver}
            onDragLeave={() => setIsDraggingDocument(false)}
            onDrop={handleDocumentDrop}
          >
            <input
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.md"
              onChange={handleDocumentPick}
            />
            <span className="admin-upload-area__icon">
              <FileUp size={26} />
            </span>
            <p>Drop documents here</p>
            <small>PDF, DOCX, TXT, or MD up to 50MB</small>
            <span className="admin-upload-btn">
              <Upload size={14} />
              Browse files
            </span>
          </label>
          {selectedDocuments.length > 0 ? (
            <div className="admin-selected-docs">
              {selectedDocuments.map((name) => (
                <span key={name}>{name}</span>
              ))}
            </div>
          ) : null}
          <p className="admin-card__section-label">Recent Documents</p>
          <div className="admin-document-list">
            {mockRecentDocuments.map((doc) => (
              <div key={doc.id} className="admin-document-item">
                <span className="admin-document-item__icon">
                  <FileText size={15} />
                </span>
                <div>
                  <strong>{doc.name}</strong>
                  <span>
                    {doc.type} <CalendarDays size={12} /> {doc.updated}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="admin-card">
          <div className="admin-card__header">
            <h2>
              <Users size={16} />
              User Management
            </h2>
            <span className="admin-badge admin-badge--blue">{users.length} users</span>
          </div>
          <div className="admin-user-list">
            {users.length === 0 ? (
              <p className="admin-empty">No users registered yet.</p>
            ) : (
              users.slice(0, 3).map((user) => (
                <div key={user.id} className="admin-user-item">
                  <div className="admin-avatar admin-avatar--xs">
                    {user.name[0]?.toUpperCase()}
                  </div>
                  <div className="admin-user-item__content">
                    <strong>{user.name}</strong>
                    <span>{user.email}</span>
                  </div>
                  <span className="admin-badge admin-badge--blue">User</span>
                </div>
              ))
            )}
          </div>
          <button type="button" className="admin-manage-link" onClick={() => navigate('/admin/users')}>
            View all users <ArrowRight size={13} />
          </button>
        </div>
      </div>

      <div className="admin-grid admin-grid--3col">
        <div className="admin-card">
          <div className="admin-card__header">
            <h2>
              <ShieldCheck size={16} />
              Roles & Permissions
            </h2>
            <button type="button" className="admin-view-all">
              View all <ArrowRight size={13} />
            </button>
          </div>
          <div className="admin-role-list">
            <div className="admin-role-item">
              <ShieldCheck size={15} style={{ color: '#2563eb' }} />
              <span>Administrators</span>
              <strong>1 admin</strong>
            </div>
            <div className="admin-role-item">
              <UserCheck size={15} style={{ color: '#14b8a6' }} />
              <span>Users</span>
              <strong>{stats?.total_users ?? 0} users</strong>
            </div>
          </div>
        </div>

        <div className="admin-card">
          <div className="admin-card__header">
            <h2>
              <Activity size={16} />
              Audit Logs
            </h2>
            <button type="button" className="admin-view-all">
              View all <ArrowRight size={13} />
            </button>
          </div>
          <div className="admin-audit-list">
            {auditLogs.length === 0 ? (
              <p className="admin-empty">No queries yet.</p>
            ) : (
              auditLogs.slice(0, 5).map((log) => (
                <div key={log.id} className="admin-audit-item">
                  <p>{log.query}</p>
                  <div className="admin-audit-item__meta">
                    <span className={gateStatusBadge(log.gateStatus)}>{log.gateStatus}</span>
                    <time>{new Date(log.createdAt).toLocaleDateString()}</time>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="admin-card">
          <div className="admin-card__header">
            <h2>
              <Zap size={16} />
              Token & AI Usage
            </h2>
          </div>
          <div className="admin-token-info">
            <strong>{stats?.total_audit_logs ?? 0}</strong>
            <span>Total AI queries</span>
          </div>
          <div className="admin-card__header" style={{ marginTop: '16px' }}>
            <h2>
              <ShieldCheck size={16} />
              System Settings
            </h2>
          </div>
          <div className="admin-settings-list">
            <button type="button" className="admin-settings-item">
              General
              <span>Configure system settings</span>
            </button>
            <button type="button" className="admin-settings-item">
              Security
              <span>Authentication and policies</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
