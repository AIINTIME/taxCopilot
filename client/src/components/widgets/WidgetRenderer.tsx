import type { ResponseWidget } from '../../types'
import { CitationsWidget } from './citations/CitationsWidget'
import { ComparisonWidget } from './comparison/ComparisonWidget'
import { LegalDraftWidget } from './legal/LegalDraftWidget'
import { MarkdownWidget } from './markdown/MarkdownWidget'
import { MetricGridWidget } from './metrics/MetricGridWidget'
import { SuggestionsWidget } from './suggestions/SuggestionsWidget'
import { TableWidgetView } from './table/TableWidgetView'
import { WarningsWidget } from './warnings/WarningsWidget'

type WidgetRendererProps = {
  widget: ResponseWidget
}

export function WidgetRenderer({ widget }: WidgetRendererProps) {
  if (widget.type === 'summary') return <MarkdownWidget widget={widget} />
  if (widget.type === 'comparison') return <ComparisonWidget widget={widget} />
  if (widget.type === 'suggestions') return <SuggestionsWidget widget={widget} />
  if (widget.type === 'warnings') return <WarningsWidget widget={widget} />
  if (widget.type === 'table') return <TableWidgetView widget={widget} />
  if (widget.type === 'legal-draft') return <LegalDraftWidget widget={widget} />
  if (widget.type === 'citations') return <CitationsWidget widget={widget} />
  if (widget.type === 'metric-grid') return <MetricGridWidget widget={widget} />
  return null
}
