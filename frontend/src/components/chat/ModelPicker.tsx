import { useEffect, useState } from 'react'
import { useChatStore } from '../../stores/chat'
import { modelsApi } from '../../api/client'

interface TextModel {
  id: string
  name: string
  provider: string
  description?: string
}

export function ModelPicker() {
  const selectedModelId = useChatStore((s) => s.selectedModelId)
  const setModel = useChatStore((s) => s.setModel)
  const [models, setModels] = useState<TextModel[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const fetchModels = async () => {
      try {
        const data = await modelsApi.getAvailableModels()
        if (cancelled) return
        const textModels: TextModel[] = data.text_models || []
        setModels(textModels)
        // Set default model if current selection is not in the list
        if (textModels.length > 0) {
          const current = useChatStore.getState().selectedModelId
          if (!textModels.find((m) => m.id === current)) {
            setModel(textModels[0].id)
          }
        }
      } catch (err) {
        console.error('Failed to load text models:', err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchModels()
    return () => { cancelled = true }
  }, [setModel])

  // Group by provider
  const grouped = models.reduce<Record<string, TextModel[]>>((acc, m) => {
    const group = m.provider === 'local' ? 'Local (Ollama)' : 'Cloud (Poe)'
    if (!acc[group]) acc[group] = []
    acc[group].push(m)
    return acc
  }, {})
  const groupOrder = ['Local (Ollama)', 'Cloud (Poe)']

  // Build flat option list with separators
  const options: React.ReactNode[] = []
  for (const group of groupOrder) {
    const groupModels = grouped[group]
    if (!groupModels || groupModels.length === 0) continue
    options.push(
      <option key={`sep-${group}`} disabled className="text-muted-foreground font-semibold text-xs">
        ─ {group} ─
      </option>
    )
    for (const m of groupModels) {
      options.push(
        <option key={m.id} value={m.id}>
          {m.name}
        </option>
      )
    }
  }

  return (
    <select
      value={selectedModelId}
      onChange={(e) => setModel(e.target.value)}
      className="w-full rounded-[8px] border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
      disabled={loading}
    >
      {loading ? (
        <option value="">Loading models...</option>
      ) : options.length === 0 ? (
        <option value="">No models available</option>
      ) : (
        options
      )}
    </select>
  )
}
