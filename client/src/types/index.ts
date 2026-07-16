export type WorkflowId = 'personal-tax' | 'corporate-tax' | 'capital-gains' | 'notices'

export type MessageRole = 'user' | 'assistant'

export type UploadStatus = 'queued' | 'uploading' | 'uploaded' | 'error'

export type AttachmentCategory = 'general' | 'government-notice' | 'supporting-docs'

export type WidgetType =
  | 'summary'
  | 'comparison'
  | 'suggestions'
  | 'warnings'
  | 'table'
  | 'legal-draft'
  | 'metric-grid'
  | 'citations'

export type GateStatus = 'VERIFIED' | 'FLAGGED' | 'PARTIAL'

export type Attachment = {
  id: string
  name: string
  size: number
  type: string
  category: AttachmentCategory
  status: UploadStatus
  progress: number
  error?: string
}

export type Workflow = {
  id: WorkflowId
  name: string
  shortName: string
  path: string
  theme: 'personal' | 'corporate' | 'gains' | 'notices'
  purpose: string
  promptPlaceholder: string
  acceptedFiles: string[]
  uploadHint: string
}

export type ComparisonMetric = {
  label: string
  value: string
}

export type ComparisonCard = {
  title: string
  badge?: string
  tone: 'neutral' | 'recommended' | 'warning'
  metrics: ComparisonMetric[]
}

export type Suggestion = {
  id: string
  label: string
  detail: string
  checked: boolean
}

export type WarningItem = {
  id: string
  title: string
  detail: string
  severity: 'low' | 'medium' | 'high'
}

export type TableWidget = {
  columns: string[]
  rows: string[][]
}

export type Metric = {
  label: string
  value: string
  trend?: string
}

export type Citation = {
  chunk_id: string
  source_id: string
  document_name: string | null
  section_reference: string | null
  excerpt: string
  confidence: number
  verified: boolean
}

export type ResponseWidget =
  | { id: string; type: 'summary'; title: string; markdown: string }
  | { id: string; type: 'comparison'; title: string; cards: ComparisonCard[] }
  | { id: string; type: 'suggestions'; title: string; items: Suggestion[] }
  | { id: string; type: 'warnings'; title: string; confidence: number; items: WarningItem[] }
  | { id: string; type: 'table'; title: string; table: TableWidget }
  | { id: string; type: 'legal-draft'; title: string; draft: string }
  | { id: string; type: 'metric-grid'; title: string; metrics: Metric[] }
  | { id: string; type: 'citations'; title: string; citations: Citation[] }

export type Message = {
  id: string
  role: MessageRole
  content: string
  createdAt: string
  attachments?: Attachment[]
  widgets?: ResponseWidget[]
  status?: 'thinking' | 'complete' | 'error'
  gateStatus?: GateStatus
  auditId?: string
}

export type Conversation = {
  id: string
  workflowId: WorkflowId
  title: string
  createdAt: string
  updatedAt: string
  messages: Message[]
}

export type SendPromptRequest = {
  conversationId: string
  workflowId: WorkflowId
  prompt: string
  attachments: Attachment[]
}

export type SendPromptResponse = {
  message: Message
  followUps: string[]
}

export type ConversationGroup = {
  label: string
  conversations: Conversation[]
}

export type ProjectKnowledgeFile = {
  id: string
  name: string
  type: string
  size: number
  uploadedAt: string
  status: 'indexed' | 'processing' | 'needs-review'
  summary: string
}

export type ProjectInstruction = {
  id: string
  title: string
  body: string
}

export type TaxProject = {
  id: string
  name: string
  detail: string
  description: string
  updatedAt: string
  files: ProjectKnowledgeFile[]
  instructions: ProjectInstruction[]
  starterPrompts: string[]
}

export type ProjectChatMessage = {
  id: string
  role: MessageRole
  content: string
  createdAt: string
}

export type ProjectChatThread = {
  id: string
  projectId: string
  title: string
  updatedAt: string
  messages: ProjectChatMessage[]
}

export type ProjectChatRequest = {
  projectId: string
  threadId: string
  prompt: string
  instructions: ProjectInstruction[]
  files: ProjectKnowledgeFile[]
}
