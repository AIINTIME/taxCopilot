import { useCallback, useEffect, useMemo, useReducer } from 'react'
import { taxApi } from '../services/api/taxApi'
import type { Attachment, AttachmentCategory, Conversation, Message, WorkflowId } from '../types'
import { createId } from '../utils/id'
import { AppStateContext, type AppContextValue, type AppState } from './appStateContext'

type AppAction =
  | { type: 'set-workflow'; workflowId: WorkflowId }
  | { type: 'set-active'; conversationId: string }
  | { type: 'upsert-conversation'; conversation: Conversation }
  | { type: 'rename-conversation'; conversationId: string; title: string }
  | { type: 'delete-conversation'; conversationId: string }
  | { type: 'add-message'; conversationId: string; message: Message }
  | { type: 'update-conversation'; conversation: Conversation }
  | { type: 'set-attachments'; attachments: Attachment[] }
  | { type: 'set-thinking'; isThinking: boolean }
  | { type: 'set-error'; error: string | null }
  | { type: 'set-follow-ups'; followUps: string[] }
  | { type: 'toggle-theme' }

const storageKey = 'taxai-client-state-v1'

const initialState: AppState = {
  conversations: [],
  activeConversationId: null,
  selectedWorkflowId: 'personal-tax',
  pendingAttachments: [],
  isThinking: false,
  error: null,
  followUps: [],
  settings: {
    darkMode: true,
  },
}

function loadState(): AppState {
  const saved = localStorage.getItem(storageKey)
  if (!saved) return initialState

  try {
    const parsed = JSON.parse(saved) as AppState
    return {
      ...initialState,
      ...parsed,
      settings: { ...initialState.settings, ...parsed.settings },
    }
  } catch {
    return initialState
  }
}

function saveState(state: AppState) {
  localStorage.setItem(
    storageKey,
    JSON.stringify({
      ...state,
      isThinking: false,
      error: null,
      pendingAttachments: state.pendingAttachments.filter((attachment) => attachment.status === 'uploaded'),
    }),
  )
}

function reducer(state: AppState, action: AppAction): AppState {
  if (action.type === 'set-workflow') {
    return { ...state, selectedWorkflowId: action.workflowId, error: null, followUps: [] }
  }

  if (action.type === 'set-active') {
    const conversation = state.conversations.find((item) => item.id === action.conversationId)
    return {
      ...state,
      activeConversationId: action.conversationId,
      selectedWorkflowId: conversation?.workflowId ?? state.selectedWorkflowId,
      error: null,
      followUps: [],
    }
  }

  if (action.type === 'upsert-conversation') {
    const exists = state.conversations.some((conversation) => conversation.id === action.conversation.id)
    const conversations = exists
      ? state.conversations.map((conversation) =>
          conversation.id === action.conversation.id ? action.conversation : conversation,
        )
      : [action.conversation, ...state.conversations]

    return { ...state, conversations, activeConversationId: action.conversation.id }
  }

  if (action.type === 'rename-conversation') {
    const title = action.title.trim()
    if (!title) return state

    return {
      ...state,
      conversations: state.conversations.map((conversation) =>
        conversation.id === action.conversationId
          ? { ...conversation, title, updatedAt: new Date().toISOString() }
          : conversation,
      ),
    }
  }

  if (action.type === 'delete-conversation') {
    const conversations = state.conversations.filter(
      (conversation) => conversation.id !== action.conversationId,
    )
    const activeConversationId = state.activeConversationId === action.conversationId
      ? conversations[0]?.id ?? null
      : state.activeConversationId

    return {
      ...state,
      conversations,
      activeConversationId,
      selectedWorkflowId: conversations.find((conversation) => conversation.id === activeConversationId)?.workflowId
        ?? state.selectedWorkflowId,
      error: null,
      followUps: [],
    }
  }

  if (action.type === 'add-message') {
    return {
      ...state,
      conversations: state.conversations.map((conversation) => {
        if (conversation.id !== action.conversationId) return conversation

        return {
          ...conversation,
          title:
            conversation.messages.length === 0 && action.message.role === 'user'
              ? action.message.content.slice(0, 46) || conversation.title
              : conversation.title,
          updatedAt: action.message.createdAt,
          messages: [...conversation.messages, action.message],
        }
      }),
    }
  }

  if (action.type === 'update-conversation') {
    return {
      ...state,
      conversations: state.conversations.map((conversation) =>
        conversation.id === action.conversation.id ? action.conversation : conversation,
      ),
    }
  }

  if (action.type === 'set-attachments') {
    return { ...state, pendingAttachments: action.attachments }
  }

  if (action.type === 'set-thinking') {
    return { ...state, isThinking: action.isThinking }
  }

  if (action.type === 'set-error') {
    return { ...state, error: action.error }
  }

  if (action.type === 'set-follow-ups') {
    return { ...state, followUps: action.followUps }
  }

  if (action.type === 'toggle-theme') {
    return { ...state, settings: { ...state.settings, darkMode: !state.settings.darkMode } }
  }

  return state
}

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, loadState)

  useEffect(() => {
    saveState(state)
    document.documentElement.dataset.theme = state.settings.darkMode ? 'dark' : 'light'
  }, [state])

  const activeConversation = useMemo(
    () => state.conversations.find((conversation) => conversation.id === state.activeConversationId) ?? null,
    [state.activeConversationId, state.conversations],
  )

  const startConversation = useCallback(
    async (workflowId = state.selectedWorkflowId) => {
      dispatch({ type: 'set-error', error: null })
      const conversation = await taxApi.createConversation(workflowId)
      dispatch({ type: 'upsert-conversation', conversation })
      dispatch({ type: 'set-workflow', workflowId })
      return conversation
    },
    [state.selectedWorkflowId],
  )

  const selectConversation = useCallback((conversationId: string) => {
    dispatch({ type: 'set-active', conversationId })
  }, [])

  const renameConversation = useCallback((conversationId: string, title: string) => {
    dispatch({ type: 'rename-conversation', conversationId, title })
  }, [])

  const deleteConversation = useCallback((conversationId: string) => {
    dispatch({ type: 'delete-conversation', conversationId })
  }, [])

  const setWorkflow = useCallback((workflowId: WorkflowId) => {
    dispatch({ type: 'set-workflow', workflowId })
  }, [])

  const uploadFiles = useCallback(
    async (files: File[], category: AttachmentCategory = 'general') => {
      const queued: Attachment[] = files.map((file) => ({
        id: createId('file'),
        name: file.name,
        size: file.size,
        type: file.type || 'application/octet-stream',
        category,
        status: 'uploading',
        progress: 35,
      }))

      dispatch({ type: 'set-attachments', attachments: [...state.pendingAttachments, ...queued] })

      const uploaded = await Promise.all(
        files.map(async (file, index) => {
          try {
            return { ...(await taxApi.uploadDocument(file)), category }
          } catch (error) {
            const message = error instanceof Error ? error.message : 'Upload failed'
            return { ...queued[index], status: 'error' as const, progress: 0, error: message }
          }
        }),
      )

      dispatch({
        type: 'set-attachments',
        attachments: [
          ...state.pendingAttachments,
          ...uploaded,
        ],
      })
    },
    [state.pendingAttachments],
  )

  const removeAttachment = useCallback(
    (attachmentId: string) => {
      dispatch({
        type: 'set-attachments',
        attachments: state.pendingAttachments.filter((attachment) => attachment.id !== attachmentId),
      })
    },
    [state.pendingAttachments],
  )

  const sendPrompt = useCallback(
    async (prompt: string) => {
      const trimmed = prompt.trim()
      if (!trimmed && state.pendingAttachments.length === 0) return

      dispatch({ type: 'set-error', error: null })
      const conversation =
        activeConversation?.workflowId === state.selectedWorkflowId
          ? activeConversation
          : await startConversation(state.selectedWorkflowId)
      const timestamp = new Date().toISOString()
      const userMessage: Message = {
        id: createId('message'),
        role: 'user',
        content: trimmed || 'Please review the attached documents.',
        createdAt: timestamp,
        attachments: state.pendingAttachments,
        status: 'complete',
      }

      dispatch({ type: 'add-message', conversationId: conversation.id, message: userMessage })
      dispatch({ type: 'set-attachments', attachments: [] })
      dispatch({ type: 'set-thinking', isThinking: true })
      dispatch({ type: 'set-follow-ups', followUps: [] })

      try {
        const response = await taxApi.sendPrompt({
          conversationId: conversation.id,
          workflowId: conversation.workflowId,
          prompt: userMessage.content,
          attachments: userMessage.attachments ?? [],
        })
        dispatch({ type: 'add-message', conversationId: conversation.id, message: response.message })
        dispatch({ type: 'set-follow-ups', followUps: response.followUps })
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Something went wrong'
        dispatch({ type: 'set-error', error: message })
      } finally {
        dispatch({ type: 'set-thinking', isThinking: false })
      }
    },
    [activeConversation, startConversation, state.pendingAttachments, state.selectedWorkflowId],
  )

  const retryLastPrompt = useCallback(async () => {
    const lastUserMessage = activeConversation?.messages.findLast((message) => message.role === 'user')
    if (lastUserMessage) {
      await sendPrompt(lastUserMessage.content)
    }
  }, [activeConversation, sendPrompt])

  const toggleTheme = useCallback(() => {
    dispatch({ type: 'toggle-theme' })
  }, [])

  const value = useMemo<AppContextValue>(
    () => ({
      ...state,
      activeConversation,
      startConversation,
      selectConversation,
      renameConversation,
      deleteConversation,
      setWorkflow,
      uploadFiles,
      removeAttachment,
      sendPrompt,
      retryLastPrompt,
      toggleTheme,
    }),
    [
      activeConversation,
      deleteConversation,
      removeAttachment,
      renameConversation,
      retryLastPrompt,
      selectConversation,
      sendPrompt,
      setWorkflow,
      startConversation,
      state,
      toggleTheme,
      uploadFiles,
    ],
  )

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>
}
