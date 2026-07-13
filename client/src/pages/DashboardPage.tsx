import { BarChart3, Newspaper } from 'lucide-react'
import { taxHighlights } from '../constants/dashboard'
import { WorkflowChooser } from '../components/workflows/WorkflowChooser'

export function DashboardPage() {
  return (
    <section className="dashboard-page">
      <div className="dashboard-hero glass-panel">
        <div>
          <p>AI Tax Copilot</p>
          <h1>Choose a tax workflow</h1>
          <span>Start with the tax area, then continue in a focused chat workspace.</span>
        </div>
        <div className="dashboard-hero__metric">
          <BarChart3 size={24} />
          <strong>4</strong>
          <span>AI workflows ready</span>
        </div>
      </div>

      <WorkflowChooser mode="navigate" />

      <section className="highlights-section">
        <div className="section-heading">
          <Newspaper size={19} />
          <div>
            <h2>Latest Tax Highlights</h2>
            <p>Static JSON-backed cards for now, ready to swap with a posts API.</p>
          </div>
        </div>
        <div className="highlight-grid">
          {taxHighlights.map((highlight) => (
            <article className="highlight-card glass-panel" key={highlight.id}>
              <div>
                <span>{highlight.category}</span>
                <small>{highlight.date}</small>
              </div>
              <h3>{highlight.title}</h3>
              <p>{highlight.summary}</p>
            </article>
          ))}
        </div>
      </section>
    </section>
  )
}
