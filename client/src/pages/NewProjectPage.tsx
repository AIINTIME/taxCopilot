import { BookOpenText, FolderPlus, Loader2, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { projectApi } from '../services/api/projectApi'

export function NewProjectPage() {
  const navigate = useNavigate()
  const [name, setName] = useState('Untitled tax project')
  const [description, setDescription] = useState('A reusable project workspace for tax files, instructions, and project chat.')
  const [instruction, setInstruction] = useState('Use uploaded files as the source of truth. Call out assumptions and missing documents before giving a final position.')
  const [isCreating, setIsCreating] = useState(false)

  async function createProject() {
    if (!name.trim()) return

    setIsCreating(true)
    const project = await projectApi.createProject({
      name: name.trim(),
      description: description.trim(),
      instruction: instruction.trim(),
    })
    setIsCreating(false)
    navigate(`/projects/${project.id}`, { state: { project } })
  }

  return (
    <section className="demo-page">
      <div className="page-intro glass-panel">
        <FolderPlus size={28} />
        <div>
          <p>New project</p>
          <h1>Create a project knowledge space</h1>
          <span>Add project instructions now, then upload files and chat inside the project.</span>
        </div>
      </div>

      <div className="new-project-layout">
        <form
          className="new-project-form glass-panel"
          onSubmit={(event) => {
            event.preventDefault()
            void createProject()
          }}
        >
          <label>
            <span>Project name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            <span>Description</span>
            <textarea value={description} rows={3} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <label>
            <span>Instructions</span>
            <textarea value={instruction} rows={6} onChange={(event) => setInstruction(event.target.value)} />
          </label>
          <button type="submit" disabled={isCreating}>
            {isCreating ? <Loader2 size={17} /> : <FolderPlus size={17} />}
            {isCreating ? 'Creating project' : 'Create project'}
          </button>
        </form>

        <aside className="new-project-preview glass-panel">
          <Sparkles size={22} />
          <h2>What this creates</h2>
          <p>A Claude-style project with persistent instructions, uploaded knowledge files, starter prompts, and project-scoped chat.</p>
          <div>
            <article>
              <BookOpenText size={17} />
              <span>Instructions are saved as API-ready JSON.</span>
            </article>
            <article>
              <FolderPlus size={17} />
              <span>Files uploaded later become reusable project knowledge.</span>
            </article>
          </div>
        </aside>
      </div>
    </section>
  )
}
