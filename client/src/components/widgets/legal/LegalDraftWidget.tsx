import { Copy, Download } from 'lucide-react'
import { useState } from 'react'
import type { ResponseWidget } from '../../../types'

type LegalDraftWidgetProps = {
  widget: Extract<ResponseWidget, { type: 'legal-draft' }>
}

export function LegalDraftWidget({ widget }: LegalDraftWidgetProps) {
  const [draft, setDraft] = useState(widget.draft)

  function downloadDraft() {
    const blob = new Blob([draft], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'notice-reply-draft.txt'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="widget legal-draft">
      <div className="widget__title-row">
        <h3>{widget.title}</h3>
        <div>
          <button type="button" onClick={() => void navigator.clipboard.writeText(draft)}>
            <Copy size={15} />
            Copy
          </button>
          <button type="button" onClick={downloadDraft}>
            <Download size={15} />
            Download
          </button>
        </div>
      </div>
      <textarea value={draft} onChange={(event) => setDraft(event.target.value)} aria-label="Editable legal reply draft" />
    </section>
  )
}
