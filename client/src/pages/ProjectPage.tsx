import {
  BookOpenText,
  Bot,
  Check,
  Database,
  FilePlus2,
  Files,
  Loader2,
  MessageSquarePlus,
  Save,
  SendHorizontal,
  Sparkles,
  UserRound,
} from 'lucide-react'
import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { Navigate, useLocation, useParams } from 'react-router-dom'
import { projectApi } from '../services/api/projectApi'
import type { ProjectChatMessage, ProjectChatThread, ProjectInstruction, ProjectKnowledgeFile, TaxProject } from '../types'
import { formatFileSize } from '../utils/format'

export function ProjectPage() {
  const { projectId } = useParams()
  const location = useLocation()
  const createdProject = (location.state as { project?: TaxProject } | null)?.project
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [project, setProject] = useState<TaxProject | null>(null)
  const [files, setFiles] = useState<ProjectKnowledgeFile[]>([])
  const [instructions, setInstructions] = useState<ProjectInstruction[]>([])
  const [threads, setThreads] = useState<ProjectChatThread[]>([])
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [prompt, setPrompt] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isUploading, setIsUploading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isThinking, setIsThinking] = useState(false)
  const [isEnhancing, setIsEnhancing] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const activeThread = threads.find((thread) => thread.id === activeThreadId) ?? threads[0]
  const messages = activeThread?.messages ?? []

  useEffect(() => {
    if (!projectId) return

    const id = projectId
    let ignore = false

    async function loadProject() {
      setIsLoading(true)
      if (createdProject?.id === id) {
        setProject(createdProject)
        setFiles(createdProject.files)
        setInstructions(createdProject.instructions)
        const thread: ProjectChatThread = {
          id: crypto.randomUUID(),
          projectId: createdProject.id,
          title: 'Getting started',
          updatedAt: 'Just now',
          messages: [
            {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: 'Project created. Upload files, adjust instructions, then ask me questions inside this project.',
              createdAt: new Date().toISOString(),
            },
          ],
        }
        setThreads([thread])
        setActiveThreadId(thread.id)
        setIsLoading(false)
        return
      }

      const [projectResponse, threadResponse] = await Promise.all([
        projectApi.getProject(id),
        projectApi.getProjectThreads(id),
      ])

      if (ignore) return

      setProject(projectResponse)
      setFiles(projectResponse?.files ?? [])
      setInstructions(projectResponse?.instructions ?? [])
      setThreads(threadResponse)
      setActiveThreadId(threadResponse[0]?.id ?? null)
      setIsLoading(false)
    }

    void loadProject()

    return () => {
      ignore = true
    }
  }, [createdProject, projectId])

  if (!projectId) {
    return <Navigate to="/" replace />
  }

  if (!isLoading && !project) {
    return <Navigate to="/" replace />
  }

  function updateInstruction(instructionId: string, body: string) {
    setInstructions((current) =>
      current.map((instruction) => (instruction.id === instructionId ? { ...instruction, body } : instruction)),
    )
  }

  async function saveInstructions() {
    if (!projectId) return
    setIsSaving(true)
    const saved = await projectApi.saveInstructions(projectId, instructions)
    setInstructions(saved)
    setIsSaving(false)
  }

  async function uploadFiles(fileList: FileList | null) {
    const incomingFiles = Array.from(fileList ?? [])
    if (incomingFiles.length === 0) return

    setIsUploading(true)
    const uploaded = await projectApi.uploadProjectFiles(incomingFiles)
    setFiles((current) => [...uploaded, ...current])
    setIsUploading(false)
  }

  function handleInputFiles(event: ChangeEvent<HTMLInputElement>) {
    void uploadFiles(event.target.files)
    event.target.value = ''
  }

  function handleDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault()
    setIsDragging(false)
    void uploadFiles(event.dataTransfer.files)
  }

  async function sendMessage(nextPrompt = prompt) {
    const trimmed = nextPrompt.trim()
    if (!trimmed || !projectId || !activeThread) return

    const userMessage: ProjectChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      createdAt: new Date().toISOString(),
    }

    setPrompt('')
    setThreads((current) =>
      current.map((thread) =>
        thread.id === activeThread.id
          ? { ...thread, title: thread.title === 'New chat' ? trimmed.slice(0, 36) : thread.title, updatedAt: 'Just now', messages: [...thread.messages, userMessage] }
          : thread,
      ),
    )
    setIsThinking(true)

    const response = await projectApi.sendProjectMessage({
      projectId,
      threadId: activeThread.id,
      prompt: trimmed,
      files,
      instructions,
    })

    setThreads((current) =>
      current.map((thread) =>
        thread.id === activeThread.id
          ? { ...thread, updatedAt: 'Just now', messages: [...thread.messages, response] }
          : thread,
      ),
    )
    setIsThinking(false)
  }

  async function enhancePrompt() {
    if (isThinking || isEnhancing || !project) return

    setIsEnhancing(true)
    const enhanced = await projectApi.enhanceProjectPrompt({
      projectName: project.name,
      prompt,
      fileCount: files.length,
      instructionCount: instructions.filter((instruction) => instruction.body.trim().length > 0).length,
    })
    setPrompt(enhanced)
    setIsEnhancing(false)
  }

  async function createProjectChat() {
    if (!projectId) return
    const thread = await projectApi.createProjectThread(projectId)
    setThreads((current) => [thread, ...current])
    setActiveThreadId(thread.id)
  }

  return (
    <section
      className={`project-workspace ${isDragging ? 'is-project-dragging' : ''}`}
      onDragOver={(event) => {
        event.preventDefault()
        setIsDragging(true)
      }}
      onDragLeave={(event) => {
        if (event.currentTarget === event.target) setIsDragging(false)
      }}
      onDrop={handleDrop}
    >
      {isDragging ? (
        <div className="project-drop-overlay" aria-hidden="true">
          <FilePlus2 size={34} />
          <strong>Drop files into this project</strong>
          <span>They will become part of the reusable project knowledge.</span>
        </div>
      ) : null}

      <aside className="project-thread-list glass-panel">
        <div className="project-thread-list__header">
          <div>
            <strong>Chats</strong>
            <span>{threads.length} in this project</span>
          </div>
          <button type="button" aria-label="New project chat" onClick={() => void createProjectChat()}>
            <MessageSquarePlus size={17} />
          </button>
        </div>
        <div className="project-thread-list__items">
          {threads.map((thread) => (
            <button
              key={thread.id}
              type="button"
              className={thread.id === activeThread?.id ? 'is-active' : ''}
              onClick={() => setActiveThreadId(thread.id)}
            >
              <span>{thread.title}</span>
              <small>{thread.messages.length} messages · {thread.updatedAt}</small>
            </button>
          ))}
        </div>
      </aside>

      <div className="project-workspace__main">
        <header className="project-hero glass-panel">
          <div>
            <p>Project knowledge space</p>
            <h1>{project?.name ?? 'Loading project'}</h1>
            <span>{project?.description ?? 'Preparing project context...'}</span>
          </div>
          <div className="project-progress">
            <Database size={24} />
            <strong>{files.length}</strong>
            <span>knowledge files</span>
          </div>
        </header>

        <section className="project-chat glass-panel">
          <div className="section-heading">
            <Bot size={19} />
            <div>
              <h2>Project chat</h2>
              <p>{activeThread?.title ?? 'Select a chat'} · answers use uploaded files and project instructions.</p>
            </div>
          </div>

          <div className="project-chat__messages" aria-live="polite">
            {messages.map((message) => (
              <article className={`project-message is-${message.role}`} key={message.id}>
                <div>{message.role === 'assistant' ? <Bot size={16} /> : <UserRound size={16} />}</div>
                <p>{message.content}</p>
              </article>
            ))}
            {isThinking ? (
              <article className="project-message is-assistant">
                <div><Loader2 size={16} /></div>
                <p>Reading project files and instructions...</p>
              </article>
            ) : null}
          </div>

          <form
            className="project-chat__composer"
            onSubmit={(event) => {
              event.preventDefault()
              void sendMessage()
            }}
          >
            <textarea
              value={prompt}
              rows={2}
              placeholder="Ask within this project..."
              onChange={(event) => setPrompt(event.target.value)}
            />
            <button
              className="project-chat__enhance"
              type="button"
              onClick={() => void enhancePrompt()}
              disabled={isThinking || isEnhancing}
            >
              {isEnhancing ? <Loader2 size={17} /> : <Sparkles size={17} />}
              Enhance
            </button>
            <button type="submit" aria-label="Send project message" disabled={isThinking || isEnhancing}>
              <SendHorizontal size={18} />
            </button>
          </form>
        </section>
      </div>

      <aside className="project-context">
        <section className="project-context-card glass-panel">
          <div className="section-heading">
            <Files size={19} />
            <div>
              <h2>Project files</h2>
              <p>Upload reusable knowledge for this project.</p>
            </div>
          </div>
          <button className="project-upload-button" type="button" onClick={() => fileInputRef.current?.click()}>
            <FilePlus2 size={17} />
            {isUploading ? 'Uploading...' : 'Upload files'}
          </button>
          <input ref={fileInputRef} type="file" multiple hidden onChange={handleInputFiles} />
          <div className="project-file-list">
            {files.map((file) => (
              <article key={file.id}>
                <div>
                  <strong>{file.name}</strong>
                  <span>{file.summary}</span>
                </div>
                <small>{file.status} · {formatFileSize(file.size)}</small>
              </article>
            ))}
          </div>
        </section>

        <section className="project-context-card glass-panel">
          <div className="section-heading">
            <BookOpenText size={19} />
            <div>
              <h2>Instructions</h2>
              <p>Persistent guidance applied to every project chat.</p>
            </div>
          </div>
          <div className="project-instruction-list">
            {instructions.map((instruction) => (
              <label key={instruction.id}>
                <span>{instruction.title}</span>
                <textarea value={instruction.body} rows={4} onChange={(event) => updateInstruction(instruction.id, event.target.value)} />
              </label>
            ))}
          </div>
          <button className="project-save-button" type="button" onClick={() => void saveInstructions()}>
            {isSaving ? <Loader2 size={16} /> : <Save size={16} />}
            {isSaving ? 'Saving' : 'Save instructions'}
          </button>
        </section>

        <section className="project-context-card glass-panel">
          <div className="section-heading">
            <Check size={19} />
            <div>
              <h2>API-ready JSON</h2>
              <p>Current project state shape.</p>
            </div>
          </div>
          <pre className="project-json-dump">
            {JSON.stringify({ projectId, fileCount: files.length, instructions, threads: threads.length, activeThreadId }, null, 2)}
          </pre>
        </section>
      </aside>
    </section>
  )
}
