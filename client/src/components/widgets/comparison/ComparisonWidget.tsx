import { BadgeCheck, CircleAlert } from 'lucide-react'
import type { ResponseWidget } from '../../../types'

type ComparisonWidgetProps = {
  widget: Extract<ResponseWidget, { type: 'comparison' }>
}

export function ComparisonWidget({ widget }: ComparisonWidgetProps) {
  return (
    <section className="widget">
      <h3>{widget.title}</h3>
      <div className="comparison-grid">
        {widget.cards.map((card) => (
          <article className={`comparison-card is-${card.tone}`} key={card.title}>
            <header>
              <h4>{card.title}</h4>
              {card.badge ? (
                <span>
                  {card.tone === 'recommended' ? <BadgeCheck size={15} /> : <CircleAlert size={15} />}
                  {card.badge}
                </span>
              ) : null}
            </header>
            <dl>
              {card.metrics.map((metric) => (
                <div key={metric.label}>
                  <dt>{metric.label}</dt>
                  <dd>{metric.value}</dd>
                </div>
              ))}
            </dl>
          </article>
        ))}
      </div>
    </section>
  )
}
