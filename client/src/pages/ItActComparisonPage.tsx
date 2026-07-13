import { ArrowRight, FileDiff, Scale } from 'lucide-react'

const comparisonRows = [
  ['Section 115BAC', 'Optional concessional regime', 'Default regime with opt-out for eligible taxpayers', 'Regime recommendation logic updated'],
  ['Section 80C', 'Broad deduction basket up to limit', 'Not available under new regime', 'Flag investments only when old regime wins'],
  ['Section 54EC', 'Bond investment exemption for long-term gains', 'Timeline and cap validation still required', 'Capital gains workflow dependency'],
  ['Section 142(1)', 'Information request from department', 'Response evidence expectations increased', 'Notice assistant draft templates'],
]

const amendmentCards = [
  { title: 'Regime defaults', value: 'New regime first', detail: 'Compare opt-out impact for salaried and business users.' },
  { title: 'Evidence burden', value: 'Higher', detail: 'Notice replies should cite source documents and computation trails.' },
  { title: 'Automation fit', value: 'Strong', detail: 'Most rule differences can be modeled as reusable eligibility checks.' },
]

export function ItActComparisonPage() {
  return (
    <section className="demo-page">
      <div className="page-intro glass-panel">
        <FileDiff size={28} />
        <div>
          <p>Static demo</p>
          <h1>IT Act comparison</h1>
          <span>Compare old provisions, current treatment, and how each change affects AI workflow decisions.</span>
        </div>
      </div>

      <div className="demo-metric-grid">
        {amendmentCards.map((card) => (
          <article className="demo-card glass-panel" key={card.title}>
            <Scale size={20} />
            <span>{card.title}</span>
            <strong>{card.value}</strong>
            <p>{card.detail}</p>
          </article>
        ))}
      </div>

      <section className="demo-table-card glass-panel">
        <div className="section-heading">
          <FileDiff size={19} />
          <div>
            <h2>Comparison matrix</h2>
            <p>Mock rule comparison table for future legal-content integrations.</p>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Section</th>
                <th>Earlier position</th>
                <th>Current position</th>
                <th>Product impact</th>
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map((row) => (
                <tr key={row[0]}>
                  {row.map((cell, index) => (
                    <td key={`${row[0]}-${cell}`}>{index === 2 ? <><ArrowRight size={14} /> {cell}</> : cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  )
}
