import { Activity, BarChart3, CircleDollarSign, TrendingUp } from 'lucide-react'

const analyticsMetrics = [
  { label: 'Active filings', value: '128', trend: '+14 this week', icon: Activity },
  { label: 'Projected savings', value: '₹42.8L', trend: 'Across 31 cases', icon: CircleDollarSign },
  { label: 'Risk reviews', value: '23', trend: '7 high priority', icon: TrendingUp },
  { label: 'AI responses', value: '1,482', trend: '96% completed', icon: BarChart3 },
]

const workflowStats = [
  { name: 'Personal tax', value: 64, color: '#2563eb' },
  { name: 'Corporate tax', value: 38, color: '#7c3aed' },
  { name: 'Capital gains', value: 29, color: '#0f766e' },
  { name: 'Notices', value: 17, color: '#d97706' },
]

export function AnalyticsPage() {
  return (
    <section className="demo-page">
      <div className="page-intro glass-panel">
        <BarChart3 size={28} />
        <div>
          <p>Static demo</p>
          <h1>Analytics</h1>
          <span>Operational snapshot of filings, savings, risk reviews, and assistant usage.</span>
        </div>
      </div>

      <div className="demo-metric-grid">
        {analyticsMetrics.map((metric) => {
          const Icon = metric.icon
          return (
            <article className="demo-card glass-panel" key={metric.label}>
              <Icon size={20} />
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <p>{metric.trend}</p>
            </article>
          )
        })}
      </div>

      <div className="analytics-layout">
        <section className="demo-table-card glass-panel">
          <div className="section-heading">
            <TrendingUp size={19} />
            <div>
              <h2>Workflow volume</h2>
              <p>Demo distribution for the last 30 days.</p>
            </div>
          </div>
          <div className="bar-list">
            {workflowStats.map((item) => (
              <div className="bar-row" key={item.name}>
                <div>
                  <span>{item.name}</span>
                  <strong>{item.value}</strong>
                </div>
                <div className="bar-track">
                  <span style={{ width: `${item.value}%`, background: item.color }} />
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="demo-table-card glass-panel">
          <div className="section-heading">
            <Activity size={19} />
            <div>
              <h2>Alerts</h2>
              <p>Mock insights surfaced by the analytics layer.</p>
            </div>
          </div>
          <div className="insight-list">
            <article><strong>GST mismatch cluster</strong><span>8 corporate projects need reconciliation before filing.</span></article>
            <article><strong>80D proof gap</strong><span>Personal tax workflows show recurring missing health policy receipts.</span></article>
            <article><strong>Notice deadline risk</strong><span>3 notices have under 10 days remaining for response.</span></article>
          </div>
        </section>
      </div>
    </section>
  )
}
