/**
 * Real client for POST /api/v1/{domain}/query, plus the mapping from the
 * backend's QueryResponse onto the widget shapes WidgetRenderer expects.
 *
 * Every figure rendered here comes from the backend's computation trace, which
 * is produced by pure Python over versioned statutory rate tables. Nothing in
 * this file invents, derives or reformats a number beyond currency formatting.
 * If a value is not in the response, it is not displayed -- the mock this
 * replaces showed a "Refund" and a deduction total that were never computed
 * from anything, which is exactly the failure mode to avoid.
 */

import { createId } from '../../utils/id'
import type { ComparisonCard, ResponseWidget, WarningItem } from '../../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export type Citation = {
  chunk_id: string
  source_id: string
  section_reference: string | null
  excerpt: string
  confidence: number
  verified: boolean
}

type TraceStep = {
  label: string
  amount: number
  section_reference: string | null
  detail: string | null
}

type ComputationTrace = {
  rule_name: string
  inputs: Record<string, unknown>
  outputs: Record<string, unknown>
  steps: TraceStep[]
  statutory_references: string[]
}

export type GateStatus = 'VERIFIED' | 'PARTIAL' | 'FLAGGED'

export type QueryResponse = {
  answer: string
  // Short extractive summary (services/rag/text_summary.py), distinct from
  // `answer` -- the summary widget uses this so it doesn't just repeat the
  // full answer already shown as the message's plain content.
  summary: string
  citations: Citation[]
  computation_trace: ComputationTrace | null
  gate_status: GateStatus
  as_of_date: string
  audit_log_id: string
  uncited_sections: string[]
  assumptions: string[]
  clarification_needed: boolean
}

function money(value: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value)
}

function num(outputs: Record<string, unknown>, key: string): number | null {
  const value = outputs[key]
  return typeof value === 'number' ? value : null
}

/**
 * The response carries no calibrated confidence, so the gate status is the only
 * honest signal available for the warnings widget's percentage. Mapped
 * explicitly rather than invented: VERIFIED means every citation checked out
 * (or a computation asserted nothing needing one), FLAGGED means citations were
 * offered and none survived verification.
 */
const GATE_CONFIDENCE: Record<GateStatus, number> = {
  VERIFIED: 100,
  PARTIAL: 60,
  FLAGGED: 30,
}

function summaryWidget(response: QueryResponse): ResponseWidget {
  const lines = [response.summary]

  if (response.assumptions.length > 0) {
    lines.push(
      '',
      '**Assumptions made** — correct any of these and the figures change:',
      ...response.assumptions.map((a) => `- ${a}`),
    )
  }

  lines.push('', `_Assessment year basis: as of ${response.as_of_date}._`)

  return {
    id: createId('widget'),
    type: 'summary',
    title: response.clarification_needed ? 'One more detail needed' : 'Summary',
    markdown: lines.join('\n'),
  }
}

function comparisonWidget(trace: ComputationTrace): ResponseWidget | null {
  const outputs = trace.outputs
  const oldTax = num(outputs, 'old_regime_tax')
  const newTax = num(outputs, 'new_regime_tax')
  if (oldTax === null || newTax === null) return null

  const recommended = outputs.recommended_regime as string | undefined

  // "either" is a real answer, not a missing one: at low incomes the Sec 87A
  // rebate zeroes both regimes and neither choice is better. Badging one as
  // Recommended would invent a preference the computation does not have.
  const card = (
    title: string,
    taxableKey: string,
    tax: number,
    isRecommended: boolean,
  ): ComparisonCard => {
    const taxable = num(outputs, taxableKey)
    return {
      title,
      tone: isRecommended ? 'recommended' : 'neutral',
      ...(isRecommended ? { badge: 'Recommended' } : {}),
      metrics: [
        ...(taxable !== null
          ? [{ label: 'Taxable Income', value: money(taxable) }]
          : []),
        { label: 'Tax Payable', value: money(tax) },
      ],
    }
  }

  return {
    id: createId('widget'),
    type: 'comparison',
    title: recommended === 'either' ? 'Regime Comparison — identical either way' : 'Regime Comparison',
    cards: [
      card('Old Regime', 'old_taxable_income', oldTax, recommended === 'old'),
      card('New Regime', 'new_taxable_income', newTax, recommended === 'new'),
    ],
  }
}

/**
 * Fallback for any rule other than personal_regime_comparison (mat, amt,
 * regime_comparison, depreciation, capital_gains, capital_gains_exemption) --
 * comparisonWidget/breakevenWidget above expect personal_regime_comparison's
 * specific output keys and return null for these, so they'd otherwise render
 * with no computation display at all. Generic metric-grid of every output.
 */
function genericComputationWidget(trace: ComputationTrace): ResponseWidget {
  const outputs = Object.entries(trace.outputs).map(([label, value]) => ({
    label,
    value: typeof value === 'number' ? String(value) : String(value ?? '—'),
  }))
  const references = trace.statutory_references

  return {
    id: createId('widget'),
    type: 'metric-grid',
    title: `Computation — ${trace.rule_name}`,
    metrics: [
      ...outputs,
      ...(references.length ? [{ label: 'Statutory references', value: references.join('; ') }] : []),
    ],
  }
}

function workingWidget(trace: ComputationTrace): ResponseWidget | null {
  if (trace.steps.length === 0) return null

  return {
    id: createId('widget'),
    type: 'table',
    title: 'How this was computed',
    table: {
      columns: ['Step', 'Amount', 'Provision'],
      rows: trace.steps.map((step) => [
        step.label,
        money(step.amount),
        step.section_reference ?? '—',
      ]),
    },
  }
}

function breakevenWidget(trace: ComputationTrace): ResponseWidget | null {
  const breakeven = num(trace.outputs, 'breakeven_deductions')
  const factors = (trace.outputs.deciding_factors as string[] | undefined) ?? []
  if (breakeven === null && factors.length === 0) return null

  const items = factors.map((factor) => ({
    id: createId('item'),
    label: factor,
    detail: '',
    checked: true,
  }))

  // The decision-relevant number when a user states income but no deductions:
  // the new regime "wins" because nothing was claimed, not because there is
  // nothing to claim.
  if (breakeven !== null) {
    items.push({
      id: createId('item'),
      label: `Old regime becomes better above ${money(breakeven)} of total deductions`,
      detail: 'Tell me about your 80C, 80D, HRA or home loan interest to refine this.',
      checked: false,
    })
  }

  return {
    id: createId('widget'),
    type: 'suggestions',
    title: 'Why this recommendation',
    items,
  }
}

function warningsWidget(response: QueryResponse): ResponseWidget | null {
  const items: WarningItem[] = []

  // A computation is VERIFIED because its figures come from pure functions over
  // versioned rate tables -- not because anything was cited. Surfacing the
  // unresolved sections keeps "verified but unsourced" visible rather than
  // silently returning an empty citation list.
  if (response.uncited_sections.length > 0) {
    items.push({
      id: createId('warn'),
      title: 'Source text unavailable for some provisions',
      detail:
        `The figures are computed from statutory rate tables, but the source text for ` +
        `${response.uncited_sections.join(', ')} is not yet in the knowledge graph, ` +
        `so these steps cannot be shown with a quotable citation.`,
      severity: 'low',
    })
  }

  if (response.gate_status === 'FLAGGED') {
    items.push({
      id: createId('warn'),
      title: 'Review required',
      detail:
        'Citations offered for this answer could not be verified against the retrieved ' +
        'sources and were removed. Have a qualified professional review before acting.',
      severity: 'high',
    })
  }

  if (items.length === 0) return null

  return {
    id: createId('widget'),
    type: 'warnings',
    title: 'Caveats',
    confidence: GATE_CONFIDENCE[response.gate_status],
    items,
  }
}

function citationsWidget(response: QueryResponse): ResponseWidget | null {
  const verified = response.citations.filter((c) => c.verified)
  if (verified.length === 0) return null

  return {
    id: createId('widget'),
    type: 'table',
    title: 'Sources',
    table: {
      columns: ['Provision', 'Cited text'],
      rows: verified.map((c) => [c.section_reference ?? '—', c.excerpt]),
    },
  }
}

export function widgetsFromQueryResponse(response: QueryResponse): ResponseWidget[] {
  const widgets: ResponseWidget[] = [summaryWidget(response)]

  // A clarification asks a question and asserts nothing. Rendering an empty
  // comparison beside it would imply a computation that never ran.
  if (response.clarification_needed) return widgets

  const trace = response.computation_trace
  if (trace) {
    const comparison = comparisonWidget(trace)
    if (comparison) {
      widgets.push(comparison)
    } else {
      widgets.push(genericComputationWidget(trace))
    }

    const breakeven = breakevenWidget(trace)
    if (breakeven) widgets.push(breakeven)

    const working = workingWidget(trace)
    if (working) widgets.push(working)
  }

  const citations = citationsWidget(response)
  if (citations) widgets.push(citations)

  const warnings = warningsWidget(response)
  if (warnings) widgets.push(warnings)

  return widgets
}

export async function queryTax(
  domain: string,
  prompt: string,
  accessToken: string | null,
): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/${domain}/query`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify({ query: prompt }),
  })

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('Your session has expired. Please log in again.')
    }
    const detail = await response.text().catch(() => '')
    throw new Error(
      detail ? `Assistant request failed: ${detail}` : 'Assistant request failed',
    )
  }

  return (await response.json()) as QueryResponse
}
