import { AnimatePresence } from 'framer-motion'
import type { Message } from '../../types'
import { MessageBubble } from './MessageBubble'

type MessageListProps = {
  messages: Message[]
}

export function MessageList({ messages }: MessageListProps) {
  return (
    <div className="message-list">
      <AnimatePresence initial={false}>
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
      </AnimatePresence>
    </div>
  )
}
