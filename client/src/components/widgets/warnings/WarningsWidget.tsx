import { AlertTriangle } from 'lucide-react'
import type { ResponseWidget } from '../../../types'

type WarningsWidgetProps = {
  widget: Extract<ResponseWidget, { type: 'warnings' }>
}

export function WarningsWidget({ widget }: WarningsWidgetProps) {
  return (
    <section className="widget">
      <div className="widget__title-row">
        <h3>{widget.title}</h3>
        <span>{widget.confidence}% confidence</span>
      </div>
      <div className="warning-list">
        {widget.items.map((item) => (
          <article className={`is-${item.severity}`} key={item.id}>
            <AlertTriangle size={17} />
            <div>
              <strong>{item.title}</strong>
              <p>{item.detail}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
