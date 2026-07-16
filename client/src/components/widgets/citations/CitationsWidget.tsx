import { BadgeCheck, ShieldQuestion } from 'lucide-react'
import type { ResponseWidget } from '../../../types'

type CitationsWidgetProps = {
  widget: Extract<ResponseWidget, { type: 'citations' }>
}

export function CitationsWidget({ widget }: CitationsWidgetProps) {
  return (
    <section className="widget">
      <div className="widget__title-row">
        <h3>{widget.title}</h3>
        <span>{widget.citations.length} source{widget.citations.length === 1 ? '' : 's'}</span>
      </div>
      <div className="citation-list">
        {widget.citations.map((citation) => (
          <article key={citation.chunk_id} className={citation.verified ? 'is-verified' : 'is-unverified'}>
            {citation.verified ? <BadgeCheck size={17} /> : <ShieldQuestion size={17} />}
            <div>
              <strong>{citation.document_name ?? citation.section_reference ?? citation.source_id}</strong>
              <p>{citation.excerpt}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
