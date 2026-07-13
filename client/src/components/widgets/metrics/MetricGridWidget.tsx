import type { ResponseWidget } from '../../../types'

type MetricGridWidgetProps = {
  widget: Extract<ResponseWidget, { type: 'metric-grid' }>
}

export function MetricGridWidget({ widget }: MetricGridWidgetProps) {
  return (
    <section className="widget">
      <h3>{widget.title}</h3>
      <div className="metric-grid">
        {widget.metrics.map((metric) => (
          <article key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            {metric.trend ? <small>{metric.trend}</small> : null}
          </article>
        ))}
      </div>
    </section>
  )
}
