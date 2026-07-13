import type { Conversation, ConversationGroup } from '../types'

const dayMs = 24 * 60 * 60 * 1000

function startOfDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}

export function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}

export function groupConversations(conversations: Conversation[]): ConversationGroup[] {
  const today = startOfDay(new Date())
  const buckets: ConversationGroup[] = [
    { label: 'Today', conversations: [] },
    { label: 'Yesterday', conversations: [] },
    { label: 'Previous 7 Days', conversations: [] },
    { label: 'Older', conversations: [] },
  ]

  conversations
    .slice()
    .sort((first, second) => Date.parse(second.updatedAt) - Date.parse(first.updatedAt))
    .forEach((conversation) => {
      const updated = startOfDay(new Date(conversation.updatedAt))
      const diff = today - updated

      if (diff < dayMs) {
        buckets[0].conversations.push(conversation)
        return
      }

      if (diff < dayMs * 2) {
        buckets[1].conversations.push(conversation)
        return
      }

      if (diff < dayMs * 8) {
        buckets[2].conversations.push(conversation)
        return
      }

      buckets[3].conversations.push(conversation)
    })

  return buckets.filter((bucket) => bucket.conversations.length > 0)
}
