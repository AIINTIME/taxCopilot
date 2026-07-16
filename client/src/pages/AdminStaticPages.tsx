import {
  Activity,
  Bell,
  CheckCircle2,
  Database,
  FileText,
  KeyRound,
  LockKeyhole,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Save,
  Trash2,
  Upload,
  Users,
  Zap,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { adminApi } from '../services/api/adminApi'
import type { PermissionItem, RoleItem } from '../services/api/adminApi'
import { useAdminAuth } from '../store/useAdminAuth'

type AdminStaticPageProps = {
  eyebrow: string
  title: string
  description: string
  icon: ReactNode
  metrics: { label: string; value: string; detail: string }[]
  primary: {
    title: string
    rows: { title: string; meta: string; status?: string }[]
  }
  secondary: {
    title: string
    items: { icon: ReactNode; title: string; detail: string }[]
  }
}

function AdminStaticPage({
  eyebrow,
  title,
  description,
  icon,
  metrics,
  primary,
  secondary,
}: AdminStaticPageProps) {
  return (
    <section className="admin-static-page">
      <div className="admin-static-hero">
        <div className="admin-static-hero__icon">{icon}</div>
        <div>
          <p>{eyebrow}</p>
          <h2>{title}</h2>
          <span>{description}</span>
        </div>
      </div>

      <div className="admin-static-metrics">
        {metrics.map((metric) => (
          <article key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <small>{metric.detail}</small>
          </article>
        ))}
      </div>

      <div className="admin-static-layout">
        <div className="admin-static-card">
          <header>
            <h3>{primary.title}</h3>
          </header>
          <div className="admin-static-list">
            {primary.rows.map((row) => (
              <article key={row.title}>
                <div>
                  <strong>{row.title}</strong>
                  <span>{row.meta}</span>
                </div>
                {row.status ? <span className="admin-badge admin-badge--blue">{row.status}</span> : null}
              </article>
            ))}
          </div>
        </div>

        <div className="admin-static-card">
          <header>
            <h3>{secondary.title}</h3>
          </header>
          <div className="admin-static-actions">
            {secondary.items.map((item) => (
              <button key={item.title} type="button">
                {item.icon}
                <span>
                  <strong>{item.title}</strong>
                  <small>{item.detail}</small>
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

export function AdminDocumentsPage() {
  return (
    <AdminStaticPage
      eyebrow="Knowledge base"
      title="Documents"
      description="Review uploaded references, ingestion status, and document coverage."
      icon={<FileText size={24} />}
      metrics={[
        { label: 'Documents', value: '24', detail: 'Static library count' },
        { label: 'Embedded', value: '18', detail: 'Ready for retrieval' },
        { label: 'In review', value: '6', detail: 'Awaiting admin approval' },
      ]}
      primary={{
        title: 'Recent Documents',
        rows: [
          { title: 'Finance Act 2025 notes.pdf', meta: 'PDF uploaded today', status: 'Embedded' },
          { title: 'Capital gains circular digest.docx', meta: 'DOCX updated yesterday', status: 'Review' },
          { title: 'Depreciation rates reference.md', meta: 'Markdown source, 12 Jul', status: 'Embedded' },
          { title: 'TDS compliance checklist.txt', meta: 'Text note, 09 Jul', status: 'Draft' },
        ],
      }}
      secondary={{
        title: 'Document Tools',
        items: [
          { icon: <Upload size={16} />, title: 'Upload queue', detail: 'Mock upload workflow' },
          { icon: <Database size={16} />, title: 'Vector coverage', detail: 'Check embedded sources' },
          { icon: <CheckCircle2 size={16} />, title: 'Review proposals', detail: 'Approve extracted rules' },
        ],
      }}
    />
  )
}

export function AdminRolesPage() {
  const { accessToken } = useAdminAuth()
  const [permissions, setPermissions] = useState<PermissionItem[]>([])
  const [roles, setRoles] = useState<RoleItem[]>([])
  const [selectedRole, setSelectedRole] = useState<RoleItem | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [permissionKeys, setPermissionKeys] = useState<string[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function loadRbac() {
    if (!accessToken) return
    setError('')
    try {
      const [nextPermissions, nextRoles] = await Promise.all([
        adminApi.getPermissions(accessToken),
        adminApi.getRoles(accessToken),
      ])
      setPermissions(nextPermissions)
      setRoles(nextRoles)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load roles')
    }
  }

  useEffect(() => {
    void loadRbac()
  }, [accessToken])

  const permissionsByCategory = useMemo(() => {
    return permissions.reduce<Record<string, PermissionItem[]>>((groups, permission) => {
      groups[permission.category] = [...(groups[permission.category] ?? []), permission]
      return groups
    }, {})
  }, [permissions])

  function resetForm() {
    setSelectedRole(null)
    setName('')
    setDescription('')
    setPermissionKeys([])
  }

  function editRole(role: RoleItem) {
    setSelectedRole(role)
    setName(role.name)
    setDescription(role.description ?? '')
    setPermissionKeys(role.permission_keys)
    setMessage('')
    setError('')
  }

  function togglePermission(key: string) {
    setPermissionKeys((current) => (
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key]
    ))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!accessToken) return

    setIsSubmitting(true)
    setError('')
    setMessage('')

    try {
      if (selectedRole) {
        const updatedRole = await adminApi.updateRole(accessToken, selectedRole.id, {
          name,
          description: description || null,
          permission_keys: permissionKeys,
        })
        setRoles((current) => current.map((role) => (role.id === updatedRole.id ? updatedRole : role)))
        setSelectedRole(updatedRole)
        setMessage(`Updated ${updatedRole.name}.`)
      } else {
        const createdRole = await adminApi.createRole(accessToken, {
          name,
          description: description || null,
          permission_keys: permissionKeys,
        })
        setRoles((current) => [...current, createdRole])
        resetForm()
        setMessage(`Created ${createdRole.name}.`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save role')
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleDelete(role: RoleItem) {
    if (!accessToken || role.is_system) return

    setIsSubmitting(true)
    setError('')
    setMessage('')
    try {
      await adminApi.deleteRole(accessToken, role.id)
      setRoles((current) => current.filter((item) => item.id !== role.id))
      if (selectedRole?.id === role.id) resetForm()
      setMessage(`Deleted ${role.name}.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to delete role')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="admin-static-page">
      <div className="admin-static-hero">
        <div className="admin-static-hero__icon"><ShieldCheck size={24} /></div>
        <div>
          <p>Permissions</p>
          <h2>Roles & Permissions</h2>
          <span>Define access levels for users across the normal workspace.</span>
        </div>
      </div>

      <div className="admin-static-metrics">
        <article><span>Roles</span><strong>{roles.length}</strong><small>Organization roles</small></article>
        <article><span>Permissions</span><strong>{permissions.length}</strong><small>Operation-level grants</small></article>
        <article><span>Assigned users</span><strong>{roles.reduce((sum, role) => sum + role.user_count, 0)}</strong><small>Role memberships</small></article>
      </div>

      {error ? <p className="admin-form-error">{error}</p> : null}
      {message ? <p className="admin-form-success"><CheckCircle2 size={14} />{message}</p> : null}

      <div className="admin-rbac-layout">
        <div className="admin-rbac-list">
          {roles.map((role) => (
            <article key={role.id} className={selectedRole?.id === role.id ? 'is-selected' : ''}>
              <button type="button" onClick={() => editRole(role)}>
                <strong>{role.name}</strong>
                <span>{role.permission_keys.length} permissions · {role.user_count} users</span>
              </button>
              <button
                type="button"
                onClick={() => void handleDelete(role)}
                disabled={role.is_system || isSubmitting}
                title={role.is_system ? 'System roles cannot be deleted' : 'Delete role'}
              >
                <Trash2 size={15} />
              </button>
            </article>
          ))}
        </div>

        <form className="admin-rbac-editor" onSubmit={handleSubmit}>
          <header>
            <div>
              <p>{selectedRole ? 'Edit role' : 'New role'}</p>
              <h3>{selectedRole?.name ?? 'Create Role'}</h3>
            </div>
            {selectedRole ? <button type="button" onClick={resetForm}>New role</button> : null}
          </header>
          <label>
            <span>Name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} minLength={2} required />
          </label>
          <label>
            <span>Description</span>
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={240} />
          </label>
          <div className="admin-permission-groups">
            {Object.entries(permissionsByCategory).map(([category, items]) => (
              <section key={category}>
                <h4>{category}</h4>
                {items.map((permission) => (
                  <label key={permission.key}>
                    <input
                      type="checkbox"
                      checked={permissionKeys.includes(permission.key)}
                      onChange={() => togglePermission(permission.key)}
                    />
                    <span>
                      <strong>{permission.label}</strong>
                      <small>{permission.description}</small>
                    </span>
                  </label>
                ))}
              </section>
            ))}
          </div>
          <button type="submit" className="admin-primary-action" disabled={isSubmitting}>
            <Save size={14} />
            {selectedRole ? 'Save role' : 'Create role'}
          </button>
        </form>
      </div>
    </section>
  )
}

export function AdminAuditLogsPage() {
  return (
    <AdminStaticPage
      eyebrow="Activity"
      title="Audit Logs"
      description="Track authentication, admin activity, document changes, and AI query events."
      icon={<Activity size={24} />}
      metrics={[
        { label: 'Events today', value: '128', detail: 'Mock event stream' },
        { label: 'Flagged', value: '3', detail: 'Needs review' },
        { label: 'Retention', value: '180d', detail: 'Static policy' },
      ]}
      primary={{
        title: 'Recent Events',
        rows: [
          { title: 'Admin reset user password', meta: '2 minutes ago from admin console', status: 'Admin' },
          { title: 'Document uploaded', meta: 'Finance Act source queued', status: 'Docs' },
          { title: 'User login succeeded', meta: 'Workspace access granted', status: 'Auth' },
          { title: 'Evidence gate flagged response', meta: 'Citation confidence below threshold', status: 'AI' },
        ],
      }}
      secondary={{
        title: 'Log Filters',
        items: [
          { icon: <LockKeyhole size={16} />, title: 'Authentication', detail: 'Login and refresh events' },
          { icon: <ShieldCheck size={16} />, title: 'Admin changes', detail: 'Access and settings updates' },
          { icon: <Zap size={16} />, title: 'AI queries', detail: 'Model and citation activity' },
        ],
      }}
    />
  )
}

export function AdminTokenUsagePage() {
  return (
    <AdminStaticPage
      eyebrow="AI operations"
      title="Token Usage"
      description="Monitor model usage, query volume, and projected consumption."
      icon={<Zap size={24} />}
      metrics={[
        { label: 'Queries', value: '1.2k', detail: 'Current month' },
        { label: 'Tokens', value: '8.4M', detail: 'Estimated usage' },
        { label: 'Budget', value: '64%', detail: 'Static monthly plan' },
      ]}
      primary={{
        title: 'Usage Breakdown',
        rows: [
          { title: 'Deep research workflows', meta: '4.1M tokens across 280 runs', status: 'High' },
          { title: 'Notice drafting', meta: '1.8M tokens across 190 runs', status: 'Normal' },
          { title: 'Comparison queries', meta: '1.4M tokens across 410 runs', status: 'Normal' },
          { title: 'Security audits', meta: '1.1M tokens across 92 runs', status: 'Low' },
        ],
      }}
      secondary={{
        title: 'Usage Controls',
        items: [
          { icon: <SlidersHorizontal size={16} />, title: 'Budget caps', detail: 'Static policy preview' },
          { icon: <Bell size={16} />, title: 'Alerts', detail: 'Notify at usage thresholds' },
          { icon: <Server size={16} />, title: 'Model routing', detail: 'Primary and fallback mix' },
        ],
      }}
    />
  )
}

export function AdminSecurityPage() {
  return (
    <AdminStaticPage
      eyebrow="Protection"
      title="Security"
      description="Review authentication posture, session settings, and account safeguards."
      icon={<ShieldCheck size={24} />}
      metrics={[
        { label: 'Alerts', value: '0', detail: 'No active threats' },
        { label: 'Sessions', value: '42', detail: 'Active user sessions' },
        { label: 'Policy', value: 'Good', detail: 'Static security score' },
      ]}
      primary={{
        title: 'Security Checks',
        rows: [
          { title: 'Refresh token rotation', meta: 'Enabled for user and admin sessions', status: 'On' },
          { title: 'Inactive account blocking', meta: 'Deactivated users cannot log in', status: 'On' },
          { title: 'CORS allowlist', meta: 'Frontend origin locked by settings', status: 'On' },
          { title: 'Profile upload constraints', meta: 'Image type and size checks enabled', status: 'On' },
        ],
      }}
      secondary={{
        title: 'Security Actions',
        items: [
          { icon: <KeyRound size={16} />, title: 'Password policy', detail: 'Minimum length enforced' },
          { icon: <Users size={16} />, title: 'Account review', detail: 'Inspect inactive users' },
          { icon: <Activity size={16} />, title: 'Audit trail', detail: 'Review sensitive events' },
        ],
      }}
    />
  )
}

export function AdminSettingsPage() {
  return (
    <AdminStaticPage
      eyebrow="Configuration"
      title="Settings"
      description="Manage organization preferences, notifications, and system defaults."
      icon={<SlidersHorizontal size={24} />}
      metrics={[
        { label: 'Organization', value: 'TaxAI', detail: 'Default workspace' },
        { label: 'Notifications', value: '6', detail: 'Static enabled channels' },
        { label: 'Integrations', value: '3', detail: 'Configured services' },
      ]}
      primary={{
        title: 'Configuration Areas',
        rows: [
          { title: 'General workspace', meta: 'Name, timezone, and branding', status: 'Ready' },
          { title: 'Notification rules', meta: 'Admin alerts and review reminders', status: 'Ready' },
          { title: 'Data retention', meta: 'Audit and document lifecycle policy', status: 'Draft' },
          { title: 'Model preferences', meta: 'Routing defaults and fallback behavior', status: 'Draft' },
        ],
      }}
      secondary={{
        title: 'Settings Shortcuts',
        items: [
          { icon: <Bell size={16} />, title: 'Notifications', detail: 'Tune alert volume' },
          { icon: <Database size={16} />, title: 'Data controls', detail: 'Retention and exports' },
          { icon: <Server size={16} />, title: 'System health', detail: 'Static service view' },
        ],
      }}
    />
  )
}
