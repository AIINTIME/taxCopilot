import { Building2, FileWarning, Landmark, WalletCards } from 'lucide-react'
import type { ComponentType } from 'react'
import { useNavigate } from 'react-router-dom'
import { workflows } from '../../constants/workflows'
import { useAppState } from '../../store/useAppState'
import type { Workflow, WorkflowId } from '../../types'

const workflowIcons: Record<WorkflowId, ComponentType<{ size?: number }>> = {
  'personal-tax': WalletCards,
  'corporate-tax': Building2,
  'capital-gains': Landmark,
  notices: FileWarning,
}

type WorkflowChooserProps = {
  mode: 'navigate' | 'new-chat'
}

export function WorkflowChooser({ mode }: WorkflowChooserProps) {
  const navigate = useNavigate()
  const { startConversation } = useAppState()

  async function chooseWorkflow(workflow: Workflow) {
    if (mode === 'new-chat') {
      await startConversation(workflow.id)
    }

    navigate(workflow.path)
  }

  return (
    <div className="workflow-chooser">
      {workflows.map((workflow) => {
        const Icon = workflowIcons[workflow.id]

        return (
          <button
            className={`workflow-choice workflow-choice--${workflow.theme}`}
            key={workflow.id}
            type="button"
            onClick={() => void chooseWorkflow(workflow)}
          >
            <span className="workflow-choice__icon">
              <Icon size={22} />
            </span>
            <span>
              <strong>{workflow.name}</strong>
              <small>{workflow.purpose}</small>
            </span>
          </button>
        )
      })}
    </div>
  )
}
