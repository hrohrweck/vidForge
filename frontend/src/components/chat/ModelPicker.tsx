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
  const [customMode, setCustomMode] = useState(false)
  const [customValue, setCustomValue] = useState('')

  useEffect(() => {
    let cancelled = false
    const fetchModels = async () => {
      try {
        const data = await modelsApi.getAvailableModels()
        if (cancelled) return
        const textModels: TextModel[] = data.text_models || []
        setModels(textModels)
        if (textModels.length > 0) {
          const current = useChatStore.getState().selectedModelId
          if (!textModels.find((m) => m.id === current) && current) {
            // Unknown model — switch to custom mode
            setCustomMode(true)
            setCustomValue(current)
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
  }, [])

  const handleSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value
    if (value === '__custom__') {
      setCustomMode(true)
      setCustomValue('')
    } else {
      setCustomMode(false)
      setModel(value)
    }
  }

  const handleCustomSubmit = () => {
    const trimmed = customValue.trim()
    if (trimmed) {
      setModel(trimmed)
    }
  }

  const handleCustomKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleCustomSubmit()
    } else if (e.key === 'Escape') {
      setCustomMode(false)
      setCustomValue('')
    }
  }

  // Group by provider
  const grouped = models.reduce<Record<string, TextModel[]>>((acc, m) => {
    const group = m.provider === 'local' ? 'Local (Ollama)' : 'Cloud'
    if (!acc[group]) acc[group] = []
    acc[group].push(m)
    return acc
  }, {})
  const groupOrder = ['Local (Ollama)', 'Cloud']

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

  // Add "Custom model..." option
  options.push(
    <option key="__custom__" value="__custom__" className="text-primary font-medium">
      ✏️ Custom model...
    </option>
  )

  if (customMode) {
    return (
      <div className="flex gap-1">
        <input
          className="flex-1 rounded-[8px] border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
          placeholder="atlascloud:deepseek-v3"
          value={customValue}
          onChange={(e) => setCustomValue(e.target.value)}
          onKeyDown={handleCustomKeyDown}
          onBlur={handleCustomSubmit}
          autoFocus
        />
        <button
          onClick={() => { setCustomMode(false); setCustomValue('') }}
          className="shrink-0 rounded-[8px] border px-2 py-2 text-xs text-muted-foreground hover:bg-muted"
        >
          ✕
        </button>
      </div>
    )
  }

  return (
    <select
      value={selectedModelId}
      onChange={handleSelectChange}
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
