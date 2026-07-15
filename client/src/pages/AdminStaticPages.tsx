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
  Upload,
  Users,
  Zap,
} from 'lucide-react'
import type { ReactNode } from 'react'

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
  return (
    <AdminStaticPage
      eyebrow="Permissions"
      title="Roles & Permissions"
      description="Define access levels for admins, reviewers, and standard users."
      icon={<ShieldCheck size={24} />}
      metrics={[
        { label: 'Admin roles', value: '3', detail: 'Owner, Admin, Reviewer' },
        { label: 'Policies', value: '12', detail: 'Static permission rules' },
        { label: 'Reviews', value: '4', detail: 'Changes awaiting sign-off' },
      ]}
      primary={{
        title: 'Role Matrix',
        rows: [
          { title: 'Owner', meta: 'Full organization and billing controls', status: 'Full' },
          { title: 'Admin', meta: 'Manage users, documents, and settings', status: 'Manage' },
          { title: 'Reviewer', meta: 'Approve document and rule proposals', status: 'Review' },
          { title: 'User', meta: 'Access tax workflows and research tools', status: 'Use' },
        ],
      }}
      secondary={{
        title: 'Permission Areas',
        items: [
          { icon: <Users size={16} />, title: 'User access', detail: 'Create and deactivate users' },
          { icon: <FileText size={16} />, title: 'Document review', detail: 'Approve source updates' },
          { icon: <KeyRound size={16} />, title: 'Credential policy', detail: 'Password reset controls' },
        ],
      }}
    />
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
