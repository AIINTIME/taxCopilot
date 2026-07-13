import { Loader2, Paperclip, SendHorizontal, Sparkles, X } from 'lucide-react'
import { useRef, useState, type ChangeEvent, type KeyboardEvent } from 'react'
import { useAutoResizeTextarea } from '../../hooks/useAutoResizeTextarea'
import { taxApi } from '../../services/api/taxApi'
import { useAppState } from '../../store/useAppState'
import type { Workflow } from '../../types'
import { formatFileSize } from '../../utils/format'

type ChatComposerProps = {
  workflow: Workflow
}

export function ChatComposer({ workflow }: ChatComposerProps) {
  const [value, setValue] = useState('')
  const [isEnhancing, setIsEnhancing] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { pendingAttachments, isThinking, uploadFiles, removeAttachment, sendPrompt } = useAppState()

  useAutoResizeTextarea(textareaRef, value)

  function readFiles(fileList: FileList | null) {
    const files = Array.from(fileList ?? [])
    if (files.length > 0) {
      void uploadFiles(files)
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    readFiles(event.target.files)
    event.target.value = ''
  }

  async function submit() {
    if (isThinking) return
    const prompt = value
    setValue('')
    await sendPrompt(prompt)
  }

  async function enhancePrompt() {
    if (isThinking || isEnhancing) return

    setIsEnhancing(true)
    const enhanced = await taxApi.enhancePrompt({
      workflowId: workflow.id,
      prompt: value,
      attachmentCount: pendingAttachments.length,
    })
    setValue(enhanced)
    setIsEnhancing(false)
    textareaRef.current?.focus()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submit()
    }
  }

  return (
    <div className="composer-shell">
      {pendingAttachments.length > 0 ? (
        <div className="attachment-row">
          {pendingAttachments.map((attachment) => (
            <div className={`attachment-chip is-${attachment.status}`} key={attachment.id}>
              <Paperclip size={14} />
              <span>{attachment.name}</span>
              <small>
                {attachment.status === 'uploading'
                  ? 'Uploading'
                  : `${attachment.category === 'government-notice' ? 'Notice' : attachment.category === 'supporting-docs' ? 'Docs' : 'File'} · ${formatFileSize(attachment.size)}`}
              </small>
              <button type="button" aria-label={`Remove ${attachment.name}`} onClick={() => removeAttachment(attachment.id)}>
                <X size={13} />
              </button>
            </div>
          ))}
        </div>
      ) : null}

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <input ref={fileInputRef} type="file" multiple hidden onChange={handleFileChange} />
        <button type="button" className="composer__icon" aria-label="Attach files" onClick={() => fileInputRef.current?.click()}>
          <Paperclip size={20} />
        </button>
        <textarea
          ref={textareaRef}
          value={value}
          rows={1}
          placeholder={workflow.promptPlaceholder}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          aria-label="Prompt"
        />
        <button
          className="composer__enhance"
          type="button"
          onClick={() => void enhancePrompt()}
          disabled={isThinking || isEnhancing}
        >
          {isEnhancing ? <Loader2 size={17} /> : <Sparkles size={17} />}
          Enhance
        </button>
        <button className="composer__send" type="submit" aria-label="Send message" disabled={isThinking || isEnhancing}>
          <SendHorizontal size={19} />
        </button>
      </form>
    </div>
  )
}
