import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, FileText, FolderOpen, RefreshCcw, UploadCloud } from 'lucide-react'
import { useState, type DragEvent } from 'react'
import { useAppState } from '../../store/useAppState'
import type { AttachmentCategory, Workflow } from '../../types'
import { MessageList } from '../messages/MessageList'
import { ChatComposer } from './ChatComposer'
import { EmptyConversation } from './EmptyConversation'
import { ThinkingIndicator } from './ThinkingIndicator'

type ChatWorkspaceProps = {
  workflow: Workflow
}

export function ChatWorkspace({ workflow }: ChatWorkspaceProps) {
  const { activeConversation, error, isThinking, retryLastPrompt, uploadFiles } = useAppState()
  const [dragCategory, setDragCategory] = useState<AttachmentCategory | null>(null)
  const messages = activeConversation?.workflowId === workflow.id ? activeConversation.messages : []

  function hasFiles(event: DragEvent<HTMLElement>) {
    return Array.from(event.dataTransfer.types).includes('Files')
  }

  function getNoticeDropCategory(event: DragEvent<HTMLElement>): AttachmentCategory {
    const bounds = event.currentTarget.getBoundingClientRect()
    const midpoint = bounds.left + bounds.width / 2
    return event.clientX < midpoint ? 'government-notice' : 'supporting-docs'
  }

  function getDropCategory(event: DragEvent<HTMLElement>): AttachmentCategory {
    return workflow.id === 'notices' ? getNoticeDropCategory(event) : 'general'
  }

  function handleDrag(event: DragEvent<HTMLElement>) {
    if (!hasFiles(event)) return
    event.preventDefault()
    setDragCategory(getDropCategory(event))
  }

  function handleDragLeave(event: DragEvent<HTMLElement>) {
    if (event.currentTarget === event.target) {
      setDragCategory(null)
    }
  }

  function handleDrop(event: DragEvent<HTMLElement>) {
    if (!hasFiles(event)) return
    event.preventDefault()
    const files = Array.from(event.dataTransfer.files)
    const category = getDropCategory(event)
    setDragCategory(null)

    if (files.length > 0) {
      void uploadFiles(files, category)
    }
  }

  return (
    <section
      className={`chat-workspace workflow-theme workflow-theme--${workflow.theme} ${dragCategory ? 'is-file-dragging' : ''}`}
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <DragUploadOverlay workflow={workflow} activeCategory={dragCategory} />

      <div className="message-scroll">
        {messages.length === 0 ? (
          <EmptyConversation workflow={workflow} />
        ) : (
          <MessageList messages={messages} />
        )}

        <AnimatePresence>
          {isThinking ? (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
            >
              <ThinkingIndicator />
            </motion.div>
          ) : null}
        </AnimatePresence>

        {error ? (
          <div className="error-banner" role="alert">
            <AlertCircle size={18} />
            <span>{error}</span>
            <button type="button" onClick={() => void retryLastPrompt()}>
              <RefreshCcw size={16} />
              Retry
            </button>
          </div>
        ) : null}
      </div>

      <ChatComposer workflow={workflow} />
    </section>
  )
}

type DragUploadOverlayProps = {
  workflow: Workflow
  activeCategory: AttachmentCategory | null
}

function DragUploadOverlay({ workflow, activeCategory }: DragUploadOverlayProps) {
  if (!activeCategory) return null

  if (workflow.id === 'notices') {
    return (
      <div className="workspace-drop-overlay workspace-drop-overlay--notice" aria-hidden="true">
        <div className={`workspace-drop-panel is-notice ${activeCategory === 'government-notice' ? 'is-active' : ''}`}>
          <FileText size={30} />
          <strong>Drop government notice</strong>
          <span>Notice, demand letter, assessment order</span>
        </div>
        <div className={`workspace-drop-panel is-docs ${activeCategory === 'supporting-docs' ? 'is-active' : ''}`}>
          <FolderOpen size={30} />
          <strong>Drop your documents</strong>
          <span>Returns, proofs, bank records, replies</span>
        </div>
      </div>
    )
  }

  return (
    <div className="workspace-drop-overlay" aria-hidden="true">
      <div className="workspace-drop-panel is-active">
        <UploadCloud size={34} />
        <strong>Drop files here</strong>
        <span>{workflow.uploadHint}</span>
      </div>
    </div>
  )
}
