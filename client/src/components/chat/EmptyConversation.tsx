import { FileText, FolderOpen, MessageSquareText, ShieldCheck, Sparkles, UploadCloud } from 'lucide-react'
import { useRef, type DragEvent } from 'react'
import { useAppState } from '../../store/useAppState'
import type { AttachmentCategory, Workflow } from '../../types'

type EmptyConversationProps = {
  workflow: Workflow
}

export function EmptyConversation({ workflow }: EmptyConversationProps) {
  const noticeInputRef = useRef<HTMLInputElement>(null)
  const docsInputRef = useRef<HTMLInputElement>(null)
  const { uploadFiles } = useAppState()

  function handleFiles(fileList: FileList | null, category: AttachmentCategory) {
    const files = Array.from(fileList ?? [])
    if (files.length > 0) {
      void uploadFiles(files, category)
    }
  }

  function handleDrop(event: DragEvent<HTMLElement>, category: AttachmentCategory) {
    event.preventDefault()
    event.stopPropagation()
    handleFiles(event.dataTransfer.files, category)
  }

  if (workflow.id === 'notices') {
    return (
      <div className="empty-state empty-state--notice">
        <div className="empty-state__icon">
          <Sparkles size={24} />
        </div>
        <h2>{workflow.name}</h2>
        <p>{workflow.purpose}</p>

        <div className="notice-upload-grid">
          <button
            type="button"
            className="notice-upload-box notice-upload-box--notice"
            onClick={() => noticeInputRef.current?.click()}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => handleDrop(event, 'government-notice')}
          >
            <FileText size={24} />
            <strong>Government notice</strong>
            <span>Drop the notice, demand letter, order, or official communication here.</span>
            <small>PDF, image, or scanned notice</small>
          </button>
          <button
            type="button"
            className="notice-upload-box notice-upload-box--docs"
            onClick={() => docsInputRef.current?.click()}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => handleDrop(event, 'supporting-docs')}
          >
            <FolderOpen size={24} />
            <strong>Your documents</strong>
            <span>Drop ITRs, bank records, proofs, ledgers, replies, or evidence here.</span>
            <small>Supporting files for the response</small>
          </button>
        </div>

        <input
          ref={noticeInputRef}
          type="file"
          multiple
          hidden
          onChange={(event) => {
            handleFiles(event.target.files, 'government-notice')
            event.target.value = ''
          }}
        />
        <input
          ref={docsInputRef}
          type="file"
          multiple
          hidden
          onChange={(event) => {
            handleFiles(event.target.files, 'supporting-docs')
            event.target.value = ''
          }}
        />
      </div>
    )
  }

  return (
    <div className="empty-state">
      <div className="empty-state__icon">
        <Sparkles size={24} />
      </div>
      <h2>{workflow.name}</h2>
      <p>{workflow.purpose}</p>
      <div className="empty-grid">
        <article>
          <UploadCloud size={18} />
          <strong>Drag files into this workspace</strong>
          <span>{workflow.uploadHint}</span>
        </article>
        <article>
          <MessageSquareText size={18} />
          <strong>Ask naturally</strong>
          <span>{workflow.promptPlaceholder}</span>
        </article>
        <article>
          <ShieldCheck size={18} />
          <strong>Review structured output</strong>
          <span>Responses arrive as summaries, cards, warnings, drafts, and checklists.</span>
        </article>
      </div>
    </div>
  )
}
