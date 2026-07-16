/**
 * Tax assistant API.
 *
 * `sendPrompt` for the personal-tax workflow now calls the real backend
 * (POST /api/v1/personal-tax/query). This file previously re-exported
 * mockTaxApi wholesale, which meant every figure on screen was a hardcoded
 * fixture: the prompt was echoed into the summary text and never touched a
 * number, so "21 lakhs" and "18 lakhs" rendered byte-identical results.
 *
 * The rest still comes from the mock, deliberately:
 *
 *   createConversation / uploadDocument / enhancePrompt
 *       No backend endpoints exist for these. Conversations are client-side
 *       only, and the upload route that does exist (/admin/documents/upload)
 *       ingests STATUTORY sources into the shared knowledge base -- it is not
 *       a place to put a user's own return.
 *
 *   corporate-tax / capital-gains / notices
 *       The computation engine only implements personal income tax (Sec
 *       115BAC old-vs-new); the corporate rules are still stubs. Routing those
 *       workflows to the real endpoint would run personal-tax rules against
 *       corporate questions and return confident nonsense -- worse than an
 *       obvious placeholder.
 */

import { mockTaxApi } from '../mock/mockTaxApi'
import { queryTax, widgetsFromQueryResponse } from './taxQueryApi'
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

async function sendPrompt(
  request: SendPromptRequest,
  accessToken: string | null,
): Promise<SendPromptResponse> {
  if (request.workflowId !== 'personal-tax') {
    return mockTaxApi.sendPrompt(request)
  }

  const response = await queryTax(request.workflowId, request.prompt, accessToken)

  const message: Message = {
    id: createId('message'),
    role: 'assistant',
    content: response.clarification_needed
      ? 'I need one more detail before I can compute this.'
      : 'I reviewed the available inputs and prepared a structured tax analysis.',
    createdAt: new Date().toISOString(),
    status: 'complete',
    widgets: widgetsFromQueryResponse(response),
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
  createConversation: mockTaxApi.createConversation,
  uploadDocument: mockTaxApi.uploadDocument,
  enhancePrompt: mockTaxApi.enhancePrompt,
  sendPrompt,
  analyzeReturn,
}
