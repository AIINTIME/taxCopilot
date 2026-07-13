import { CheckCircle2, Clock3, KeyRound, LockKeyhole, ShieldCheck } from 'lucide-react'

const controls = [
  { label: 'Document encryption', status: 'Enabled', icon: LockKeyhole },
  { label: 'Role-based access', status: 'Configured', icon: KeyRound },
  { label: 'Audit logging', status: 'Active', icon: ShieldCheck },
  { label: 'Session review', status: 'Scheduled', icon: Clock3 },
]

const auditEvents = [
  ['11:42', 'Ananya Kapoor uploaded AIS Extract.xlsx', 'Document'],
  ['10:16', 'TaxAI generated notice reply draft', 'AI Action'],
  ['09:40', 'Finance Team reviewed GST mismatch report', 'Review'],
  ['Yesterday', 'Admin updated project access policy', 'Security'],
]

export function SecurityAuditPage() {
  return (
    <section className="demo-page">
      <div className="page-intro glass-panel">
        <LockKeyhole size={28} />
        <div>
          <p>Static demo</p>
          <h1>Security and Audit</h1>
          <span>Mock controls, access status, and audit trail for secure tax document workflows.</span>
        </div>
      </div>

      <div className="demo-metric-grid">
        {controls.map((control) => {
          const Icon = control.icon
          return (
            <article className="demo-card glass-panel" key={control.label}>
              <Icon size={20} />
              <span>{control.label}</span>
              <strong>{control.status}</strong>
              <p><CheckCircle2 size={14} /> Policy check passing</p>
            </article>
          )
        })}
      </div>

      <section className="demo-table-card glass-panel">
        <div className="section-heading">
          <ShieldCheck size={19} />
          <div>
            <h2>Audit trail</h2>
            <p>Static activity feed showing how compliance actions will be tracked.</p>
          </div>
        </div>
        <div className="audit-feed">
          {auditEvents.map(([time, event, type]) => (
            <article key={`${time}-${event}`}>
              <span>{time}</span>
              <strong>{event}</strong>
              <small>{type}</small>
            </article>
          ))}
        </div>
      </section>
    </section>
  )
}
