import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { ChatWorkspace } from '../components/chat/ChatWorkspace'
import { workflowFromPath } from '../constants/workflows'
import { useAppState } from '../store/useAppState'

export function WorkflowPage() {
  const location = useLocation()
  const workflow = workflowFromPath(location.pathname)
  const { setWorkflow } = useAppState()

  useEffect(() => {
    setWorkflow(workflow.id)
  }, [setWorkflow, workflow.id])

  return <ChatWorkspace workflow={workflow} />
}
