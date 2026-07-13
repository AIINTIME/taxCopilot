import { MessageSquarePlus } from 'lucide-react'
import { WorkflowChooser } from '../components/workflows/WorkflowChooser'

export function NewChatPage() {
  return (
    <section className="new-chat-page">
      <div className="page-intro glass-panel">
        <MessageSquarePlus size={26} />
        <div>
          <p>New chat</p>
          <h1>Select a tax assistant</h1>
          <span>Pick the workflow first so uploads, widgets, prompts, and colors are tuned for the task.</span>
        </div>
      </div>
      <WorkflowChooser mode="new-chat" />
    </section>
  )
}
