import { projectChatDumps, projectDumps } from '../../constants/projectDumps'
import type { ProjectChatMessage, ProjectChatRequest, ProjectChatThread, ProjectInstruction, ProjectKnowledgeFile, TaxProject } from '../../types'
import { createId } from '../../utils/id'

const delay = (minimum = 350, maximum = 850) =>
  new Promise((resolve) => {
    window.setTimeout(resolve, minimum + Math.random() * (maximum - minimum))
  })

function now() {
  return new Date().toISOString()
}

export const mockProjectApi = {
  async listProjects(): Promise<TaxProject[]> {
    await delay(200, 450)
    return projectDumps
  },

  async getProject(projectId: string): Promise<TaxProject | null> {
    await delay()
    return projectDumps.find((project) => project.id === projectId) ?? null
  },

  async getProjectThreads(projectId: string): Promise<ProjectChatThread[]> {
    await delay(250, 500)
    return projectChatDumps[projectId] ?? []
  },

  async createProjectThread(projectId: string): Promise<ProjectChatThread> {
    await delay(250, 500)
    return {
      id: createId('project-thread'),
      projectId,
      title: 'New chat',
      updatedAt: 'Just now',
      messages: [
        {
          id: createId('project-message'),
          role: 'assistant',
          content: 'New project chat started. I will use the same project files and instructions for this thread.',
          createdAt: now(),
        },
      ],
    }
  },

  async uploadProjectFiles(files: File[]): Promise<ProjectKnowledgeFile[]> {
    await delay(650, 1200)
    return files.map((file) => ({
      id: createId('project-file'),
      name: file.name,
      type: file.type || 'Uploaded file',
      size: file.size,
      uploadedAt: 'Just now',
      status: 'processing',
      summary: 'Uploaded to project knowledge. Indexing is simulated and ready for backend replacement.',
    }))
  },

  async createProject(input: { name: string; description: string; instruction: string }): Promise<TaxProject> {
    await delay(450, 900)

    return {
      id: createId('project'),
      name: input.name,
      detail: 'Custom knowledge space',
      description: input.description,
      updatedAt: 'Just now',
      files: [],
      instructions: [
        {
          id: createId('instruction'),
          title: 'Project instructions',
          body: input.instruction,
        },
      ],
      starterPrompts: [
        'Summarize the project files and instructions.',
        'What should I upload next?',
        'Create a working checklist from this project.',
      ],
    }
  },

  async saveInstructions(projectId: string, instructions: ProjectInstruction[]): Promise<ProjectInstruction[]> {
    await delay(300, 650)
    void projectId
    return instructions
  },

  async enhanceProjectPrompt(input: {
    projectName: string
    prompt: string
    fileCount: number
    instructionCount: number
  }): Promise<string> {
    await delay(500, 900)
    const basePrompt = input.prompt.trim() || 'Help me analyze this project.'

    return `Use the "${input.projectName}" project context to improve this request before answering.

Project context available:
- ${input.fileCount} knowledge file${input.fileCount === 1 ? '' : 's'}
- ${input.instructionCount} active instruction block${input.instructionCount === 1 ? '' : 's'}

Please answer with project-grounded reasoning, cite assumptions, identify missing files, and separate facts from recommendations.

User request:
${basePrompt}`
  },

  async sendProjectMessage(request: ProjectChatRequest): Promise<ProjectChatMessage> {
    await delay(850, 1400)
    const fileCount = request.files.length
    const instructionCount = request.instructions.filter((instruction) => instruction.body.trim().length > 0).length

    return {
      id: createId('project-message'),
      role: 'assistant',
      createdAt: now(),
      content: `Using this project's ${fileCount} knowledge file${fileCount === 1 ? '' : 's'} and ${instructionCount} instruction block${instructionCount === 1 ? '' : 's'} in this chat, here is the working answer:\n\n${request.prompt}\n\nI would ground the response in the uploaded project context, call out assumptions, and ask for any missing source document before giving a final filing or reply position.`,
    }
  },
}
