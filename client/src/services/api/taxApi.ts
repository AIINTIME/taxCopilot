/**
 * Tax assistant API. `sendPrompt` calls the real backend
 * (POST /api/v1/{workflowId}/query) for every workflow -- corporate-tax,
 * capital-gains and personal-tax all have real computation rules wired up
 * (see backend/app/services/computation/engine.py's RULES), so none of them
 * are routed to the mock. `analyzeReturn` (upload a filed ITR, get back
 * discrepancies + an AI score) is a separate, additional capability.
 *
 * createConversation / uploadDocument / enhancePrompt still come from the
 * mock: no backend endpoint exists for these. Conversations are client-side
 * only, and the upload route that does exist (/admin/documents/upload)
 * ingests STATUTORY sources into the shared knowledge base -- it is not a
 * place to put a user's own return (that's what analyzeReturn is for).
 */

import { mockTaxApi } from '../mock/mockTaxApi'
import { queryTax, queryTaxWithDocument, widgetsFromQueryResponse, type QueryResponse } from './taxQueryApi'
import { analyzeReturn as analyzeReturnRequest, widgetsFromAnalyzeResponse } from './analyzeReturnApi'
import { createId } from '../../utils/id'
import type { Message, SendPromptRequest, SendPromptResponse } from '../../types'

const CLARIFICATION_FOLLOW_UPS = [
  'It is salary income.',
  'It is business or professional income.',
]

const DEFAULT_FOLLOW_UPS = [
  'What changes if I add another deduction proof?',
  'Which documents are still missing?',
  'Can you turn this into a filing checklist?',
]

function sendPromptResponseFromQuery(response: QueryResponse): SendPromptResponse {
  const message: Message = {
    id: createId('message'),
    role: 'assistant',
    content: response.answer,
    createdAt: new Date().toISOString(),
    status: 'complete',
    widgets: widgetsFromQueryResponse(response),
    gateStatus: response.gate_status,
    auditId: response.audit_log_id,
  }

  return {
    message,
    // When the backend has asked a question, "what changes if I add a deduction
    // proof?" is noise -- the useful follow-ups are answers to what it asked.
    followUps: response.clarification_needed
      ? CLARIFICATION_FOLLOW_UPS
      : DEFAULT_FOLLOW_UPS,
  }
}

async function sendPrompt(
  request: SendPromptRequest,
  accessToken: string | null,
): Promise<SendPromptResponse> {
  const response = await queryTax(request.workflowId, request.prompt, accessToken)
  return sendPromptResponseFromQuery(response)
}

// Companion to sendPrompt for a question asked alongside an attached
// document, on any workflow -- see taxQueryApi.ts's queryTaxWithDocument.
async function sendPromptWithDocument(
  request: SendPromptRequest,
  file: File,
  accessToken: string | null,
): Promise<SendPromptResponse> {
  const response = await queryTaxWithDocument(request.workflowId, request.prompt, file, accessToken)
  return sendPromptResponseFromQuery(response)
}

async function analyzeReturn(
  file: File,
  accessToken: string | null,
): Promise<SendPromptResponse> {
  const response = await analyzeReturnRequest(file, accessToken)

  const message: Message = {
    id: createId('message'),
    role: 'assistant',
    content: response.usable
      ? 'I reviewed your return and checked it against the statute.'
      : 'I need a little more detail to review this return.',
    createdAt: new Date().toISOString(),
    status: 'complete',
    widgets: widgetsFromAnalyzeResponse(response),
  }

  return {
    message,
    followUps: response.usable
      ? [
          'Which regime should I have filed under?',
          'How do I fix the over-claimed deduction?',
          'What is my correct tax payable?',
        ]
      : ['My income is …', 'I filed under the old regime', 'I filed under the new regime'],
  }
}

export const taxApi = {
  ...mockTaxApi,
  sendPrompt,
  sendPromptWithDocument,
  analyzeReturn,
}
