import { BrainCircuit, Check, Loader2, SearchCheck, SendHorizontal } from 'lucide-react'
import { useMemo, useState } from 'react'
import { deepResearchApi, researchModels } from '../services/api/deepResearchApi'
import type { ResearchResponse } from '../services/mock/mockDeepResearchApi'

export function DeepResearchPage() {
  const [selectedModels, setSelectedModels] = useState<string[]>(['gpt-5', 'claude-opus'])
  const [prompt, setPrompt] = useState('Compare the tax risk and documentation needs for choosing the old regime with HRA, 80C, and capital gains.')
  const [responses, setResponses] = useState<ResearchResponse[]>([])
  const [isRunning, setIsRunning] = useState(false)

  const selectedCount = selectedModels.length
  const responseGridStyle = useMemo(
    () => ({
      gridTemplateColumns: `repeat(${Math.max(1, Math.min(selectedCount || responses.length || 1, 4))}, minmax(260px, 1fr))`,
    }),
    [responses.length, selectedCount],
  )

  function toggleModel(modelId: string) {
    setSelectedModels((current) => {
      if (current.includes(modelId)) {
        return current.length === 1 ? current : current.filter((id) => id !== modelId)
      }

      return [...current, modelId]
    })
  }

  async function runResearch() {
    if (!prompt.trim() || selectedModels.length === 0) return

    setIsRunning(true)
    const result = await deepResearchApi.runResearch({
      prompt: prompt.trim(),
      modelIds: selectedModels,
    })
    setResponses(result)
    setIsRunning(false)
  }

  return (
    <section className="deep-research-page">
      <div className="page-intro glass-panel">
        <BrainCircuit size={28} />
        <div>
          <p>Deep research</p>
          <h1>Compare multiple LLM answers</h1>
          <span>Select which models to run, submit one prompt, then review the responses side by side.</span>
        </div>
      </div>

      <section className="deep-research-control glass-panel">
        <div className="section-heading">
          <SearchCheck size={19} />
          <div>
            <h2>Research setup</h2>
            <p>{selectedModels.length} model{selectedModels.length === 1 ? '' : 's'} selected</p>
          </div>
        </div>

        <div className="model-picker">
          {researchModels.map((model) => {
            const isSelected = selectedModels.includes(model.id)

            return (
              <button
                key={model.id}
                type="button"
                className={isSelected ? 'is-selected' : ''}
                onClick={() => toggleModel(model.id)}
              >
                <span>{isSelected ? <Check size={15} /> : null}</span>
                <strong>{model.name}</strong>
                <small>{model.provider} - {model.tone}</small>
              </button>
            )
          })}
        </div>

        <form
          className="deep-research-form"
          onSubmit={(event) => {
            event.preventDefault()
            void runResearch()
          }}
        >
          <textarea value={prompt} rows={5} onChange={(event) => setPrompt(event.target.value)} />
          <button type="submit" disabled={isRunning}>
            {isRunning ? <Loader2 size={17} /> : <SendHorizontal size={17} />}
            {isRunning ? 'Researching' : 'Run research'}
          </button>
        </form>
      </section>

      {responses.length > 0 ? (
        <section className="research-response-grid" style={responseGridStyle}>
          {responses.map((response) => (
            <article className="research-card glass-panel" key={response.id}>
              <header>
                <div>
                  <span>{response.provider}</span>
                  <h2>{response.modelName}</h2>
                </div>
              </header>
              <p>{response.summary}</p>
              <div>
                <h3>Key points</h3>
                <ul>
                  {response.keyPoints.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h3>Caveats</h3>
                <ul>
                  {response.caveats.map((caveat) => (
                    <li key={caveat}>{caveat}</li>
                  ))}
                </ul>
              </div>
            </article>
          ))}
        </section>
      ) : null}
    </section>
  )
}
