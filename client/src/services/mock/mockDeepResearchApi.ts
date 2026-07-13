import { createId } from '../../utils/id'

export type ResearchModel = {
  id: string
  name: string
  provider: string
  tone: string
}

export type ResearchResponse = {
  id: string
  modelId: string
  modelName: string
  provider: string
  summary: string
  keyPoints: string[]
  caveats: string[]
}

export const researchModels: ResearchModel[] = [
  { id: 'gpt-5', name: 'GPT-5', provider: 'OpenAI', tone: 'Structured reasoning' },
  { id: 'claude-opus', name: 'Claude Opus', provider: 'Anthropic', tone: 'Long-form synthesis' },
  { id: 'gemini-pro', name: 'Gemini Pro', provider: 'Google', tone: 'Source-oriented scan' },
  { id: 'llama-4', name: 'Llama 4', provider: 'Meta', tone: 'Concise alternate view' },
]

const delay = (minimum = 850, maximum = 1500) =>
  new Promise((resolve) => {
    window.setTimeout(resolve, minimum + Math.random() * (maximum - minimum))
  })

export const mockDeepResearchApi = {
  async runResearch(input: { prompt: string; modelIds: string[] }): Promise<ResearchResponse[]> {
    await delay()

    return input.modelIds.map((modelId, index) => {
      const model = researchModels.find((item) => item.id === modelId) ?? researchModels[0]

      return {
        id: createId('research-response'),
        modelId: model.id,
        modelName: model.name,
        provider: model.provider,
        summary: `${model.name} frames the research request as a tax and compliance investigation. It prioritizes ${model.tone.toLowerCase()} while keeping the answer grounded in the user's prompt: "${input.prompt}".`,
        keyPoints: [
          index % 2 === 0
            ? 'Separate statutory interpretation from filing-position recommendations.'
            : 'Start with the taxpayer facts, then map each fact to evidence and risk.',
          'Identify missing documents before recommending a final treatment.',
          'Compare conservative and optimized positions so the user can choose risk appetite.',
        ],
        caveats: [
          'This is a mock model response for frontend testing.',
          'A production version should include source citations and model run metadata.',
        ],
      }
    })
  },
}
