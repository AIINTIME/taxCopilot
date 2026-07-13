import type { ProjectChatThread, TaxProject } from '../types'

export const projectDumps: TaxProject[] = [
  {
    id: 'project-fy26',
    name: 'FY 2025-26 Filing',
    detail: 'Personal tax knowledge space',
    description: 'Reusable context for salary, deductions, AIS entries, capital gains, and filing preferences.',
    updatedAt: 'Today',
    files: [
      {
        id: 'file-form16',
        name: 'Form 16 - Employer A.pdf',
        type: 'Salary',
        size: 1_860_000,
        uploadedAt: 'Today',
        status: 'indexed',
        summary: 'Salary, TDS, exemptions, and employer-provided deductions.',
      },
      {
        id: 'file-ais',
        name: 'AIS Extract.xlsx',
        type: 'Income statement',
        size: 820_000,
        uploadedAt: 'Yesterday',
        status: 'indexed',
        summary: 'Interest, dividends, securities transactions, and reported TDS credits.',
      },
      {
        id: 'file-broker',
        name: 'Broker Statement.csv',
        type: 'Capital gains',
        size: 540_000,
        uploadedAt: 'Previous 7 Days',
        status: 'needs-review',
        summary: 'Equity and mutual fund transactions requiring ISIN mapping.',
      },
    ],
    instructions: [
      {
        id: 'instruction-style',
        title: 'Response style',
        body: 'Explain tax positions in concise language first, then show calculation details and assumptions.',
      },
      {
        id: 'instruction-preference',
        title: 'Filing preference',
        body: 'Prefer lower-risk positions unless tax savings are material and document support is strong.',
      },
    ],
    starterPrompts: [
      'Compare old and new regime using only project files.',
      'Which proofs are missing before filing?',
      'Create a final filing checklist from this project.',
    ],
  },
  {
    id: 'project-gst',
    name: 'Q1 GST Reconciliation',
    detail: 'Corporate tax knowledge space',
    description: 'Company-specific context for GST mismatches, turnover reconciliation, audit notes, and ledgers.',
    updatedAt: 'Yesterday',
    files: [
      {
        id: 'file-gstr1',
        name: 'GSTR-1_Q1.json',
        type: 'GST',
        size: 1_240_000,
        uploadedAt: 'Yesterday',
        status: 'indexed',
        summary: 'Invoice-level outward supply data for Q1.',
      },
      {
        id: 'file-ledger',
        name: 'Sales Ledger.xlsx',
        type: 'Books',
        size: 2_760_000,
        uploadedAt: 'Yesterday',
        status: 'processing',
        summary: 'Book turnover and customer-wise sales ledger.',
      },
    ],
    instructions: [
      {
        id: 'instruction-corp-risk',
        title: 'Risk threshold',
        body: 'Highlight mismatches above Rs. 25,000 and separate timing differences from true exceptions.',
      },
      {
        id: 'instruction-output',
        title: 'Output format',
        body: 'Give the finance team a reconciliation table, root cause, and action owner for each item.',
      },
    ],
    starterPrompts: [
      'Find likely GST mismatches from the project files.',
      'Draft reconciliation notes for audit review.',
      'What files should the finance team upload next?',
    ],
  },
  {
    id: 'project-notice',
    name: 'Notice Reply Pack',
    detail: 'Notice response knowledge space',
    description: 'Project context for notice facts, uploaded evidence, reply tone, and draft response strategy.',
    updatedAt: 'Today',
    files: [
      {
        id: 'file-notice',
        name: 'Notice u/s 143(1).pdf',
        type: 'Government notice',
        size: 640_000,
        uploadedAt: 'Today',
        status: 'indexed',
        summary: 'Mismatch notice comparing AIS entries and return disclosures.',
      },
      {
        id: 'file-bank',
        name: 'Bank Credit Proof.pdf',
        type: 'Evidence',
        size: 940_000,
        uploadedAt: 'Today',
        status: 'indexed',
        summary: 'Bank statements supporting disputed transaction source.',
      },
    ],
    instructions: [
      {
        id: 'instruction-reply',
        title: 'Reply posture',
        body: 'Keep the response respectful, point-wise, evidence-backed, and avoid admitting liability.',
      },
      {
        id: 'instruction-annexures',
        title: 'Annexures',
        body: 'Every factual assertion in the draft should cite an uploaded file or identify missing evidence.',
      },
    ],
    starterPrompts: [
      'Draft a point-wise response using project files.',
      'What evidence is missing for this notice?',
      'Summarize the notice risk in plain English.',
    ],
  },
]

export const projectChatDumps: Record<string, ProjectChatThread[]> = {
  'project-fy26': [
    {
      id: 'thread-fy26-regime',
      projectId: 'project-fy26',
      title: 'Regime comparison',
      updatedAt: 'Today',
      messages: [
        {
          id: 'project-message-fy26-1',
          role: 'assistant',
          content: 'I have indexed the salary, AIS, and broker files. Ask me to compare regimes, verify deductions, or produce a filing checklist.',
          createdAt: '2026-07-10T08:30:00.000Z',
        },
      ],
    },
    {
      id: 'thread-fy26-docs',
      projectId: 'project-fy26',
      title: 'Missing documents',
      updatedAt: 'Yesterday',
      messages: [
        {
          id: 'project-message-fy26-2',
          role: 'assistant',
          content: 'This thread can track proof gaps such as medical insurance receipts, rent proof, and broker acquisition values.',
          createdAt: '2026-07-09T08:30:00.000Z',
        },
      ],
    },
  ],
  'project-gst': [
    {
      id: 'thread-gst-reco',
      projectId: 'project-gst',
      title: 'GST reconciliation',
      updatedAt: 'Today',
      messages: [
        {
          id: 'project-message-gst-1',
          role: 'assistant',
          content: 'The GST project is ready. I can compare GSTR data against ledgers and separate timing differences from true mismatches.',
          createdAt: '2026-07-10T08:30:00.000Z',
        },
      ],
    },
  ],
  'project-notice': [
    {
      id: 'thread-notice-draft',
      projectId: 'project-notice',
      title: 'Reply draft',
      updatedAt: 'Today',
      messages: [
        {
          id: 'project-message-notice-1',
          role: 'assistant',
          content: 'The notice and evidence files are indexed. I can draft replies, identify missing annexures, and explain the risk.',
          createdAt: '2026-07-10T08:30:00.000Z',
        },
      ],
    },
  ],
}
