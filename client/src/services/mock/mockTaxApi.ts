import { workflowById } from '../../constants/workflows'
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

const delay = (minimum = 900, maximum = 1800) =>
  new Promise((resolve) => {
    window.setTimeout(resolve, minimum + Math.random() * (maximum - minimum))
  })

function maybeFail(operation: string) {
  if (Math.random() < 0.04) {
    throw new Error(`${operation} failed. Please retry.`)
  }
}

function now() {
  return new Date().toISOString()
}

function money(value: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value)
}

function baseSummary(workflowId: WorkflowId, prompt: string): ResponseWidget {
  const workflow = workflowById[workflowId]

  return {
    id: createId('widget'),
    type: 'summary',
    title: 'Summary',
    markdown: `Based on the documents and prompt, I reviewed this as a **${workflow.name}** case. The current facts suggest a moderate opportunity to improve the filing position while keeping supporting evidence organized.\n\nUser context considered: _${prompt || workflow.promptPlaceholder}_`,
  }
}

function personalWidgets(prompt: string): ResponseWidget[] {
  return [
    baseSummary('personal-tax', prompt),
    {
      id: createId('widget'),
      type: 'comparison',
      title: 'Regime Comparison',
      cards: [
        {
          title: 'Old Regime',
          tone: 'recommended',
          badge: 'Recommended',
          metrics: [
            { label: 'Taxable Income', value: money(1_120_000) },
            { label: 'Deductions', value: money(245_000) },
            { label: 'Tax', value: money(118_500) },
            { label: 'Surcharge', value: money(0) },
            { label: 'Cess', value: money(4_740) },
            { label: 'Final Payable', value: money(123_240) },
            { label: 'Refund', value: money(18_600) },
          ],
        },
        {
          title: 'New Regime',
          tone: 'neutral',
          metrics: [
            { label: 'Taxable Income', value: money(1_365_000) },
            { label: 'Deductions', value: money(75_000) },
            { label: 'Tax', value: money(132_000) },
            { label: 'Surcharge', value: money(0) },
            { label: 'Cess', value: money(5_280) },
            { label: 'Final Payable', value: money(137_280) },
            { label: 'Refund', value: money(4_560) },
          ],
        },
      ],
    },
    {
      id: createId('widget'),
      type: 'suggestions',
      title: 'Suggested Actions',
      items: [
        { id: createId('item'), label: 'Claim HRA', detail: 'Rent proof and landlord PAN can improve old regime outcome.', checked: true },
        { id: createId('item'), label: 'Use 80C', detail: 'Validate ELSS, PF, insurance, and tuition fee proofs.', checked: true },
        { id: createId('item'), label: 'Claim 80D', detail: 'Medical insurance receipts appear missing from the upload set.', checked: false },
        { id: createId('item'), label: 'Report interest income', detail: 'Cross-check AIS savings and fixed deposit interest.', checked: false },
      ],
    },
    {
      id: createId('widget'),
      type: 'warnings',
      title: 'Missing Documents',
      confidence: 82,
      items: [
        { id: createId('warn'), title: 'Capital gains statement needed', detail: 'Mutual fund sale mentioned but broker statement is not attached.', severity: 'medium' },
        { id: createId('warn'), title: 'Rent receipts incomplete', detail: 'Only nine months of rent evidence was detected.', severity: 'low' },
      ],
    },
  ]
}

function corporateWidgets(prompt: string): ResponseWidget[] {
  return [
    baseSummary('corporate-tax', prompt),
    {
      id: createId('widget'),
      type: 'comparison',
      title: 'Liability Scenarios',
      cards: [
        {
          title: 'Current Liability',
          tone: 'warning',
          metrics: [
            { label: 'Book Profit', value: money(8_700_000) },
            { label: 'Tax Liability', value: money(2_262_000) },
            { label: 'Compliance Exposure', value: 'High' },
          ],
        },
        {
          title: 'Optimized Liability',
          tone: 'recommended',
          badge: 'Recommended',
          metrics: [
            { label: 'Adjusted Profit', value: money(8_140_000) },
            { label: 'Tax Liability', value: money(2_116_400) },
            { label: 'Estimated Saving', value: money(145_600) },
          ],
        },
      ],
    },
    {
      id: createId('widget'),
      type: 'metric-grid',
      title: 'Risk Signals',
      metrics: [
        { label: 'Risk Score', value: '68 / 100', trend: 'Medium-high' },
        { label: 'GST Mismatch', value: money(320_000), trend: 'Needs reconciliation' },
        { label: 'TDS Variance', value: money(74_000), trend: 'Review ledger mapping' },
      ],
    },
    {
      id: createId('widget'),
      type: 'suggestions',
      title: 'Recommended Next Steps',
      items: [
        { id: createId('item'), label: 'Reconcile GST turnover', detail: 'Compare books, GSTR-1, and GSTR-3B before filing.', checked: false },
        { id: createId('item'), label: 'Review depreciation', detail: 'Asset block additions may be eligible for improved treatment.', checked: true },
        { id: createId('item'), label: 'Prepare audit notes', detail: 'Document management estimates and related-party positions.', checked: false },
      ],
    },
  ]
}

function gainsWidgets(prompt: string): ResponseWidget[] {
  return [
    baseSummary('capital-gains', prompt),
    {
      id: createId('widget'),
      type: 'table',
      title: 'Capital Gain Calculation',
      table: {
        columns: ['Particular', 'Amount'],
        rows: [
          ['Sale consideration', money(8_950_000)],
          ['Indexed acquisition cost', money(4_280_000)],
          ['Transfer expenses', money(180_000)],
          ['Long-term capital gain', money(4_490_000)],
          ['Estimated tax', money(897_000)],
        ],
      },
    },
    {
      id: createId('widget'),
      type: 'comparison',
      title: 'Exemption Impact',
      cards: [
        {
          title: 'Without Exemptions',
          tone: 'warning',
          metrics: [
            { label: 'Taxable Gain', value: money(4_490_000) },
            { label: 'Tax Estimate', value: money(933_000) },
          ],
        },
        {
          title: 'With Exemptions',
          tone: 'recommended',
          badge: 'Recommended',
          metrics: [
            { label: 'Taxable Gain', value: money(2_150_000) },
            { label: 'Tax Estimate', value: money(447_000) },
            { label: 'Potential Saving', value: money(486_000) },
          ],
        },
      ],
    },
    {
      id: createId('widget'),
      type: 'suggestions',
      title: 'Exemption Opportunities',
      items: [
        { id: createId('item'), label: 'Section 54F', detail: 'Check residential investment timeline and ownership conditions.', checked: false },
        { id: createId('item'), label: 'Section 54EC', detail: 'Bond investment can reduce taxable long-term gains.', checked: false },
        { id: createId('item'), label: 'Carry forward losses', detail: 'Broker statement suggests prior year losses may be available.', checked: true },
      ],
    },
  ]
}

function noticeWidgets(prompt: string): ResponseWidget[] {
  return [
    baseSummary('notices', prompt),
    {
      id: createId('widget'),
      type: 'comparison',
      title: 'Notice Review',
      cards: [
        {
          title: 'What Went Wrong',
          tone: 'warning',
          metrics: [
            { label: 'Mismatch Type', value: 'AIS vs ITR' },
            { label: 'Demand Exposure', value: money(86_400) },
            { label: 'Response Window', value: '21 days' },
          ],
        },
        {
          title: 'How To Resolve',
          tone: 'recommended',
          badge: 'Action plan',
          metrics: [
            { label: 'Evidence Needed', value: 'Broker note, bank proof' },
            { label: 'Reply Strength', value: 'Good' },
            { label: 'Recommended Filing', value: 'Online response' },
          ],
        },
      ],
    },
    {
      id: createId('widget'),
      type: 'legal-draft',
      title: 'Reply Draft',
      draft:
        'To\nThe Assessing Officer,\n\nSubject: Response to notice regarding variance in reported income\n\nRespected Sir/Madam,\n\nWe submit that the variance mentioned in point 2 appears to arise from duplicate reporting in the information statement. The taxpayer has reported the actual transaction value in the return of income and has attached supporting broker statements and bank credit records for verification.\n\nWe request your office to consider the enclosed documents and drop the proposed adjustment. We remain available to provide any further clarification required.\n\nSincerely,\nTaxpayer',
    },
    {
      id: createId('widget'),
      type: 'warnings',
      title: 'Evidence Gaps',
      confidence: 76,
      items: [
        { id: createId('warn'), title: 'Attach source statement', detail: 'The reply is stronger with the original AIS/TIS extract.', severity: 'medium' },
        { id: createId('warn'), title: 'Confirm deadline', detail: 'The notice date was not machine-readable in the upload.', severity: 'high' },
      ],
    },
  ]
}

function widgetsForWorkflow(workflowId: WorkflowId, prompt: string): ResponseWidget[] {
  if (workflowId === 'corporate-tax') return corporateWidgets(prompt)
  if (workflowId === 'capital-gains') return gainsWidgets(prompt)
  if (workflowId === 'notices') return noticeWidgets(prompt)
  return personalWidgets(prompt)
}

export const mockTaxApi = {
  async createConversation(workflowId: WorkflowId): Promise<Conversation> {
    await delay(250, 500)
    const timestamp = now()

    return {
      id: createId('conversation'),
      workflowId,
      title: `New ${workflowById[workflowId].shortName} chat`,
      createdAt: timestamp,
      updatedAt: timestamp,
      messages: [],
    }
  },

  async uploadDocument(file: File): Promise<Attachment> {
    await delay(650, 1200)
    maybeFail('Upload')

    return {
      id: createId('file'),
      name: file.name,
      size: file.size,
      type: file.type || 'application/octet-stream',
      category: 'general',
      status: 'uploaded',
      progress: 100,
    }
  },

  async enhancePrompt(input: { workflowId: WorkflowId; prompt: string; attachmentCount: number }): Promise<string> {
    await delay(500, 900)
    const workflow = workflowById[input.workflowId]
    const basePrompt = input.prompt.trim() || workflow.promptPlaceholder
    const attachmentContext =
      input.attachmentCount > 0
        ? `I have uploaded ${input.attachmentCount} supporting file${input.attachmentCount === 1 ? '' : 's'}.`
        : 'I have not uploaded supporting files yet.'

    return `Act as an expert ${workflow.name} assistant. ${attachmentContext}

Please analyse the facts below, identify missing documents, state assumptions, and provide a structured response with calculations or draft language where relevant.

Facts and request:
${basePrompt}`
  },

  async sendPrompt(request: SendPromptRequest): Promise<SendPromptResponse> {
    await delay(1100, 1900)
    maybeFail('Assistant response')

    const message: Message = {
      id: createId('message'),
      role: 'assistant',
      content: 'I reviewed the available inputs and prepared a structured tax analysis.',
      createdAt: now(),
      status: 'complete',
      widgets: widgetsForWorkflow(request.workflowId, request.prompt),
    }

    return {
      message,
      followUps: [
        'What changes if I add another deduction proof?',
        'Which documents are still missing?',
        'Can you turn this into a filing checklist?',
      ],
    }
  },
}
