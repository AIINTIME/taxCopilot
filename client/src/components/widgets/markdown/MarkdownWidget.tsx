import ReactMarkdown from 'react-markdown'
import type { ResponseWidget } from '../../../types'

type MarkdownWidgetProps = {
  widget: Extract<ResponseWidget, { type: 'summary' }>
}

export function MarkdownWidget({ widget }: MarkdownWidgetProps) {
  return (
    <section className="widget">
      <h3>{widget.title}</h3>
      <div className="markdown-body">
        <ReactMarkdown>{widget.markdown}</ReactMarkdown>
      </div>
    </section>
  )
}
