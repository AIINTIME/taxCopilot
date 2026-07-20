import { createContext } from 'react'
import type { Attachment, AttachmentCategory, Conversation, WorkflowId } from '../types'

export type AppSettings = {
  darkMode: boolean
}

export type AppState = {
  conversations: Conversation[]
  activeConversationId: string | null
  selectedWorkflowId: WorkflowId
  pendingAttachments: Attachment[]
  isThinking: boolean
  error: string | null
  followUps: string[]
  settings: AppSettings
}

export type AppContextValue = AppState & {
  activeConversation: Conversation | null
  startConversation: (workflowId?: WorkflowId) => Promise<Conversation>
  selectConversation: (conversationId: string) => void
  renameConversation: (conversationId: string, title: string) => void
  deleteConversation: (conversationId: string) => void
  setWorkflow: (workflowId: WorkflowId) => void
  uploadFiles: (files: File[], category?: AttachmentCategory) => Promise<void>
  removeAttachment: (attachmentId: string) => void
  sendPrompt: (prompt: string) => Promise<void>
  retryLastPrompt: () => Promise<void>
  regenerateResponse: (assistantMessageId: string) => Promise<void>
  toggleTheme: () => void
}

export const AppStateContext = createContext<AppContextValue | null>(null)
