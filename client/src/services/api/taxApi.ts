import { mockTaxApi } from '../mock/mockTaxApi'
import type { Citation, GateStatus, Message, ResponseWidget, SendPromptRequest, SendPromptResponse } from '../../types'
import { createId } from '../../utils/id'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

type QueryResponse = {
  answer: string
  summary: string
  citations: Citation[]
  computation_trace: Record<string, unknown> | null
  gate_status: GateStatus
  as_of_date: string
  audit_log_id: string
}

async function postQuery(domain: string, accessToken: string, query: string): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/${domain}/query`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ query }),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? 'Something went wrong')
  }

  return response.json() as Promise<QueryResponse>
}

function computationTraceWidget(trace: Record<string, unknown>): ResponseWidget {
  const outputs = (trace.outputs as Record<string, unknown>) ?? {}
  const references = (trace.statutory_references as string[]) ?? []

  return {
    id: createId('widget'),
    type: 'metric-grid',
    title: `Computation — ${String(trace.rule_name ?? 'result')}`,
    metrics: [
      ...Object.entries(outputs).map(([label, value]) => ({ label, value: String(value) })),
      ...(references.length ? [{ label: 'Statutory references', value: references.join('; ') }] : []),
    ],
  }
}

function gateWarningWidget(gateStatus: GateStatus): ResponseWidget {
  const isFlagged = gateStatus === 'FLAGGED'
  return {
    id: createId('widget'),
    type: 'warnings',
    title: isFlagged ? 'Needs Review' : 'Partially Verified',
    confidence: isFlagged ? 0 : 60,
    items: [
      {
        id: createId('warn'),
        title: isFlagged ? 'Unverified or missing sources' : 'Some claims unverified',
        detail: isFlagged
          ? 'This response could not be fully grounded in the Knowledge Graph — treat it as a starting point, not a final answer.'
          : 'Some claims in this response could not be verified against retrieved sources and were flagged.',
        severity: isFlagged ? 'high' : 'medium',
      },
    ],
  }
}

function widgetsFromResponse(result: QueryResponse): ResponseWidget[] {
  const widgets: ResponseWidget[] = [
    { id: createId('widget'), type: 'summary', title: 'Summary', markdown: result.summary },
  ]

  if (result.computation_trace) {
    widgets.push(computationTraceWidget(result.computation_trace))
  }

  if (result.citations.length > 0) {
    widgets.push({ id: createId('widget'), type: 'citations', title: 'Sources', citations: result.citations })
  }

  if (result.gate_status !== 'VERIFIED') {
    widgets.push(gateWarningWidget(result.gate_status))
  }

  return widgets
}

export const taxApi = {
  ...mockTaxApi,
  async sendPrompt(request: SendPromptRequest, accessToken: string): Promise<SendPromptResponse> {
    const result = await postQuery(request.workflowId, accessToken, request.prompt)

    const message: Message = {
      id: createId('message'),
      role: 'assistant',
      content: result.answer,
      createdAt: new Date().toISOString(),
      status: 'complete',
      widgets: widgetsFromResponse(result),
      gateStatus: result.gate_status,
      auditId: result.audit_log_id,
    }

    return { message, followUps: [] }
  },
}
