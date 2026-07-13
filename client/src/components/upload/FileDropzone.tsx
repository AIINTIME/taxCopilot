import { UploadCloud } from 'lucide-react'
import type { Workflow } from '../../types'

type FileDropzoneProps = {
  workflow: Workflow
  isActive: boolean
}

export function FileDropzone({ workflow, isActive }: FileDropzoneProps) {
  return (
    <div className={`dropzone ${isActive ? 'is-active' : ''}`} aria-hidden={!isActive}>
      <UploadCloud size={20} />
      <span>Drop files for {workflow.shortName}</span>
      <small>{workflow.acceptedFiles.join(', ')}</small>
    </div>
  )
}
