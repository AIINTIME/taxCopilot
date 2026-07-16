/**
 * Real client for POST /api/v1/personal-tax/analyze-return, plus the mapping
 * from the backend's AnalyzeReturnResponse onto the widget shapes the renderer
 * already knows.
 *
 * As with taxQueryApi, nothing here invents a figure. The discrepancies, their
 * source lines, and the score all come from the backend's reconciler and are
 * rendered verbatim. Penalties are deliberately not shown even as an empty
 * section beyond a one-line note, because they depend on the rule graph, which
 * is not populated yet.
 */

import { createId } from '../../utils/id'
import type { Metric, ResponseWidget, WarningItem } from '../../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

type DiscrepancyOut = {
  type: string
  severity: 'high' | 'medium' | 'low'
  section_reference: string | null
  summary: string
  declared: number | null
  correct: number | null
  cost: number | null
  source_line: string | null
}

type ScoreOut = {
  accuracy: number
  risk: number
  grade: string
  overall: number
  findings: number
  exposure: number
  explanation: string[]
}

export type AnalyzeReturnResponse = {
  usable: boolean
  missing: string[]
  clarification: string | null
  declared: Record<string, unknown>
  discrepancies: DiscrepancyOut[]
  score: ScoreOut | null
  penalties: unknown[]
  as_of_date: string
}

function money(value: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value)
}

const _TITLES: Record<string, string> = {
  excess_deduction: 'Deduction over the statutory cap',
  disallowed_deduction: 'Deduction not allowed in this regime',
  tax_mismatch: 'Declared tax does not match the return',
  suboptimal_regime: 'A different regime would cost less',
}

function summaryWidget(response: AnalyzeReturnResponse): ResponseWidget {
  if (!response.usable) {
    return {
      id: createId('widget'),
      type: 'summary',
      title: 'More detail needed',
      markdown:
        response.clarification ??
        'I could not read enough from this document to analyse it.',
    }
  }

  const s = response.score!
  const headline =
    s.findings === 0
      ? 'No problems found against the return’s own figures.'
      : `Found ${s.findings} issue${s.findings === 1 ? '' : 's'} in this return.`

  return {
    id: createId('widget'),
    type: 'summary',
    title: 'Return review',
    markdown: [
      headline,
      '',
      ...s.explanation.map((line) => `- ${line}`),
      '',
      `_Assessed as of ${response.as_of_date}. Penalty exposure is not shown — ` +
        `the statutory penalty graph is not available yet._`,
    ].join('\n'),
  }
}

function scoreWidget(score: ScoreOut): ResponseWidget {
  // risk is "higher is worse" on the backend; label it so the number is not
  // read as a positive.
  const metrics: Metric[] = [
    { label: 'Overall', value: `${score.overall}/100`, trend: `Grade ${score.grade}` },
    { label: 'Accuracy', value: `${score.accuracy}/100` },
    { label: 'Risk (lower is better)', value: `${score.risk}/100` },
    { label: 'Tax at stake', value: money(score.exposure) },
  ]
  return { id: createId('widget'), type: 'metric-grid', title: 'AI score', metrics }
}

function discrepancyWidget(discrepancies: DiscrepancyOut[]): ResponseWidget | null {
  if (discrepancies.length === 0) return null

  const items: WarningItem[] = discrepancies.map((d) => ({
    id: createId('warn'),
    title: _TITLES[d.type] ?? d.type,
    // The source line is the "where it went wrong" -- appended so each finding
    // points at the line in the return it refers to.
    detail: d.source_line ? `${d.summary}\n\nIn your return: “${d.source_line}”` : d.summary,
    severity: d.severity,
  }))

  return {
    id: createId('widget'),
    type: 'warnings',
    title: 'Where it went wrong',
    confidence: 100,
    items,
  }
}

function declaredVsCorrectWidget(discrepancies: DiscrepancyOut[]): ResponseWidget | null {
  // Only findings that actually have a declared-vs-correct pair. The regime
  // recommendation has no single "declared number" to tabulate.
  const rows = discrepancies
    .filter((d) => d.declared != null && d.correct != null)
    .map((d) => [
      d.section_reference ?? _TITLES[d.type] ?? d.type,
      money(d.declared as number),
      money(d.correct as number),
      d.source_line ?? '—',
    ])

  if (rows.length === 0) return null

  return {
    id: createId('widget'),
    type: 'table',
    title: 'Declared vs. correct',
    table: { columns: ['Item', 'You declared', 'Should be', 'Where'], rows },
  }
}

export function widgetsFromAnalyzeResponse(response: AnalyzeReturnResponse): ResponseWidget[] {
  const widgets: ResponseWidget[] = [summaryWidget(response)]
  if (!response.usable) return widgets

  if (response.score) widgets.push(scoreWidget(response.score))

  const discrepancies = discrepancyWidget(response.discrepancies)
  if (discrepancies) widgets.push(discrepancies)

  const table = declaredVsCorrectWidget(response.discrepancies)
  if (table) widgets.push(table)

  return widgets
}

export async function analyzeReturn(
  file: File,
  accessToken: string | null,
): Promise<AnalyzeReturnResponse> {
  const form = new FormData()
  form.append('file', file)

  const response = await fetch(`${API_BASE_URL}/api/v1/personal-tax/analyze-return`, {
    method: 'POST',
    credentials: 'include',
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    body: form,
  })

  if (!response.ok) {
    if (response.status === 401) throw new Error('Your session has expired. Please log in again.')
    const detail = await response.text().catch(() => '')
    throw new Error(detail ? `Analysis failed: ${detail}` : 'Analysis failed')
  }

  return (await response.json()) as AnalyzeReturnResponse
}
