import { mockTaxApi } from '../mock/mockTaxApi'
import { API_BASE_URL } from './authApi'
import { getAccessToken } from './authToken'
import type {
  Attachment,
  Conversation,
  Message,
  ResponseWidget,
  SendPromptRequest,
  SendPromptResponse,
  WorkflowId,
} from '../../types'
import { createId } from '../../utils/id'

type BackendQueryResponse = {
  answer: string
  citations: unknown[]
  computation_trace: { rule_name: string; outputs: Record<string, unknown> } | null
  ground_truth_check: { verified: boolean; mismatches: string[] } | null
  gate_status: string
  as_of_date: string
  audit_log_id: string
}

// Builds a visible "which path did this take" widget from the backend's flat
// response -- computation_trace is only ever present when the COMPUTATION
// node ran; its absence means this went through RETRIEVAL only. This is the
// literal signal for "is it hitting computation or retrieval or both."
function widgetsFromBackendResponse(response: BackendQueryResponse): ResponseWidget[] {
  const widgets: ResponseWidget[] = [
    {
      id: createId('widget'),
      type: 'summary',
      title: 'Summary',
      markdown: response.answer || '_No answer text returned._',
    },
  ]

  if (response.computation_trace) {
    const outputs = response.computation_trace.outputs ?? {}
    widgets.push({
      id: createId('widget'),
      type: 'table',
      title: `Computation result (${response.computation_trace.rule_name})`,
      table: {
        columns: ['Field', 'Value'],
        rows: Object.entries(outputs).map(([key, value]) => [key, String(value)]),
      },
    })
  }

  const pathTaken = response.computation_trace ? 'Computation (+ ground-truth check)' : 'Retrieval / advisory'
  const groundTruthNote = response.ground_truth_check
    ? response.ground_truth_check.verified
      ? 'corroborated by knowledge graph/vector store'
      : response.ground_truth_check.mismatches.length > 0
        ? `mismatch flagged: ${response.ground_truth_check.mismatches[0]}`
        : 'no ground truth available yet for this rule'
    : 'not applicable (no computation ran)'

  widgets.push({
    id: createId('widget'),
    type: 'metric-grid',
    title: 'Flow / verification status',
    metrics: [
      { label: 'Path taken', value: pathTaken },
      { label: 'Gate status', value: response.gate_status },
      { label: 'Ground truth', value: groundTruthNote },
      { label: 'Citations found', value: String(response.citations.length) },
    ],
  })

  return widgets
}

async function sendPrompt(request: SendPromptRequest): Promise<SendPromptResponse> {
  const token = getAccessToken()
  if (!token) throw new Error('You need to log in again')

  const response = await fetch(`${API_BASE_URL}/api/v1/${request.workflowId}/query`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    // Free text only for now -- there is no deterministic parser turning a
    // typed sentence into computation_request's structured fields yet, so a
    // plain question always goes through the RETRIEVAL path. Sending a
    // computation_request here (once a form/parser exists) is what would
    // route this through COMPUTATION instead.
    body: JSON.stringify({ query: request.prompt }),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? 'Something went wrong')
  }

  const data = (await response.json()) as BackendQueryResponse

  const message: Message = {
    id: createId('message'),
    role: 'assistant',
    content: data.answer || 'No answer text returned.',
    createdAt: new Date().toISOString(),
    status: 'complete',
    widgets: widgetsFromBackendResponse(data),
  }

  return {
    message,
    followUps: [
      'What changes if I add another deduction proof?',
      'Which documents are still missing?',
      'Can you turn this into a filing checklist?',
    ],
  }
}

export const taxApi = {
  // No backend concept of a persisted conversation yet -- kept local, same
  // as the mock, just to keep the chat UI's data model working.
  async createConversation(workflowId: WorkflowId): Promise<Conversation> {
    const timestamp = new Date().toISOString()
    return {
      id: createId('conversation'),
      workflowId,
      title: `New chat`,
      createdAt: timestamp,
      updatedAt: timestamp,
      messages: [],
    }
  },

  // Not wired to the backend yet -- there is no upload endpoint that turns a
  // file into UserQueryDocument + extracted text (services/rag/extraction/
  // document_extraction.py only runs on uploaded_document_text already
  // present in a /query call, not on a standalone upload). Kept local/
  // cosmetic like the mock until that endpoint exists.
  async uploadDocument(file: File): Promise<Attachment> {
    return mockTaxApi.uploadDocument(file)
  },

  // Cosmetic prompt-rewriting helper, unrelated to the backend's computation/
  // retrieval logic -- no corresponding endpoint, kept as the mock's.
  enhancePrompt: mockTaxApi.enhancePrompt,

  sendPrompt,
}
