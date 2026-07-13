import type { Workflow, WorkflowId } from '../types'

export const workflows: Workflow[] = [
  {
    id: 'personal-tax',
    name: 'Personal Income Tax',
    shortName: 'Personal',
    path: '/personal-tax',
    theme: 'personal',
    purpose: 'Analyse salary, investments, deductions, and regime fit.',
    promptPlaceholder: 'I have HRA and sold one mutual fund.',
    acceptedFiles: ['PDF', 'Images', 'Excel', 'CSV'],
    uploadHint: 'Upload Form 16, AIS, investment proofs, rent receipts, or broker statements.',
  },
  {
    id: 'corporate-tax',
    name: 'Corporate Tax',
    shortName: 'Corporate',
    path: '/corporate',
    theme: 'corporate',
    purpose: 'Review company financials, compliance issues, and optimization paths.',
    promptPlaceholder: 'Review our P&L and GST filings for tax optimization.',
    acceptedFiles: ['Balance Sheet', 'P&L', 'GST', 'Audit Reports'],
    uploadHint: 'Upload balance sheet, P&L, GST data, audit notes, and schedules.',
  },
  {
    id: 'capital-gains',
    name: 'Capital Gains',
    shortName: 'Gains',
    path: '/capital-gains',
    theme: 'gains',
    purpose: 'Calculate capital gains and evaluate exemptions.',
    promptPlaceholder: 'I sold property and reinvested part of the proceeds.',
    acceptedFiles: ['Property Docs', 'Broker Statements', 'Sale Agreements'],
    uploadHint: 'Upload broker reports, purchase records, sale deeds, or exemption proof.',
  },
  {
    id: 'notices',
    name: 'Government Notice Assistant',
    shortName: 'Notices',
    path: '/notices',
    theme: 'notices',
    purpose: 'Explain notices and draft structured replies.',
    promptPlaceholder: 'We disagree with point 2 in the notice.',
    acceptedFiles: ['Notice', 'Supporting Docs', 'Evidence'],
    uploadHint: 'Upload the notice, demand letter, prior filings, and supporting evidence.',
  },
]

export const workflowById = workflows.reduce<Record<WorkflowId, Workflow>>(
  (accumulator, workflow) => {
    accumulator[workflow.id] = workflow
    return accumulator
  },
  {
    'personal-tax': workflows[0],
    'corporate-tax': workflows[1],
    'capital-gains': workflows[2],
    notices: workflows[3],
  },
)

export function workflowFromPath(pathname: string): Workflow {
  return workflows.find((workflow) => workflow.path === pathname) ?? workflows[0]
}
