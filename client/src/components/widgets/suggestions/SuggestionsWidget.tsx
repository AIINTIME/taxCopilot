import { CheckCircle2, Circle } from 'lucide-react'
import type { ResponseWidget } from '../../../types'

type SuggestionsWidgetProps = {
  widget: Extract<ResponseWidget, { type: 'suggestions' }>
}

export function SuggestionsWidget({ widget }: SuggestionsWidgetProps) {
  return (
    <section className="widget">
      <h3>{widget.title}</h3>
      <div className="suggestion-list">
        {widget.items.map((item) => (
          <article key={item.id}>
            {item.checked ? <CheckCircle2 size={18} /> : <Circle size={18} />}
            <div>
              <strong>{item.label}</strong>
              <p>{item.detail}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
