import { motion } from 'framer-motion'
import { Bot, Check, Copy, RotateCcw, ThumbsDown, ThumbsUp, UserRound } from 'lucide-react'
import type { Message } from '../../types'
import { formatTime } from '../../utils/date'
import { formatFileSize } from '../../utils/format'
import { WidgetRenderer } from '../widgets/WidgetRenderer'

type MessageBubbleProps = {
  message: Message
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isAssistant = message.role === 'assistant'

  return (
    <motion.article
      className={`message ${isAssistant ? 'message--assistant' : 'message--user'}`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.18 }}
    >
      <div className="message__avatar" aria-hidden="true">
        {isAssistant ? <Bot size={18} /> : <UserRound size={18} />}
      </div>
      <div className="message__body">
        <header>
          <strong>{isAssistant ? 'TaxAI' : 'You'}</strong>
          <time>{formatTime(message.createdAt)}</time>
        </header>
        <p>{message.content}</p>

        {message.attachments && message.attachments.length > 0 ? (
          <div className="message-attachments">
            {message.attachments.map((attachment) => (
              <span key={attachment.id}>
                <Check size={13} />
                {attachment.name}
                <small>
                  {attachment.category === 'government-notice'
                    ? 'Notice'
                    : attachment.category === 'supporting-docs'
                      ? 'Docs'
                      : 'File'}{' '}
                  · {formatFileSize(attachment.size)}
                </small>
              </span>
            ))}
          </div>
        ) : null}

        {message.widgets ? (
          <div className="widget-stack">
            {message.widgets.map((widget) => (
              <WidgetRenderer key={widget.id} widget={widget} />
            ))}
          </div>
        ) : null}

        {isAssistant ? (
          <footer className="message-actions">
            <button type="button">
              <Copy size={15} />
              Copy
            </button>
            <button type="button">
              <RotateCcw size={15} />
              Regenerate
            </button>
            <button type="button" aria-label="Helpful">
              <ThumbsUp size={15} />
            </button>
            <button type="button" aria-label="Not helpful">
              <ThumbsDown size={15} />
            </button>
          </footer>
        ) : null}
      </div>
    </motion.article>
  )
}
