import { useEffect, useState } from 'react'
import { useChatStore } from '../../stores/chat'
import { modelsApi } from '../../api/client'

interface TextModel {
  id: string
  name: string
  provider: string
  provider_type?: string
  description?: string
  capabilities?: Record<string, boolean>
}

export function ModelPicker() {
  const selectedModelId = useChatStore((s) => s.selectedModelId)
  const defaultModelId = useChatStore((s) => s.defaultModelId)
  const setModel = useChatStore((s) => s.setModel)
  const fetchDefaultModel = useChatStore((s) => s.fetchDefaultModel)
  const setDefaultModel = useChatStore((s) => s.setDefaultModel)
  const [models, setModels] = useState<TextModel[]>([])
  const [loading, setLoading] = useState(true)
  const [customMode, setCustomMode] = useState(false)
  const [customValue, setCustomValue] = useState('')
  const [settingDefault, setSettingDefault] = useState(false)

  useEffect(() => {
    let cancelled = false
    const fetchModels = async () => {
      try {
        // Fetch default model from server
        await fetchDefaultModel()

        // Try the dedicated chat models endpoint first
        let chatModels: TextModel[]
        try {
          chatModels = await modelsApi.getChatModels() as TextModel[]
        } catch {
          // Fallback: use /available and filter client-side
          const data = await modelsApi.getAvailableModels()
          const textModels: TextModel[] = data.text_models || []
          chatModels = textModels.filter(m => {
            const c = m.capabilities
            if (!c || Array.isArray(c)) return false
            return c.accepts_text === true && c.accepts_image === true && c.outputs_text === true
          })
        }
        if (cancelled) return
        setModels(chatModels)
        if (chatModels.length > 0) {
          const current = useChatStore.getState().selectedModelId
          if (!chatModels.find((m) => m.id === current) && current) {
            // Unknown model — switch to custom mode
            setCustomMode(true)
            setCustomValue(current)
          }
        }
      } catch (err) {
        // Silently ignore — model picker falls back to custom mode
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchModels()
    return () => { cancelled = true }
  }, [fetchDefaultModel])

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

  const handleSetDefault = async () => {
    if (!selectedModelId || settingDefault) return
    setSettingDefault(true)
    try {
      await setDefaultModel(selectedModelId)
    } catch {
      // Error already logged in store
    } finally {
      setSettingDefault(false)
    }
  }

  // Group by provider type
  const grouped = models.reduce<Record<string, TextModel[]>>((acc, m) => {
    const group = m.provider_type === 'ollama' ? 'Ollama (Local)' :
                  m.provider_type === 'poe' ? 'Poe' :
                  m.provider_type === 'atlascloud' ? 'AtlasCloud' :
                  m.provider || 'Other'
    if (!acc[group]) acc[group] = []
    acc[group].push(m)
    return acc
  }, {})
  const groupOrder = ['Ollama (Local)', 'Poe', 'AtlasCloud', 'Other']

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
      const isDefault = m.id === defaultModelId
      options.push(
        <option key={m.id} value={m.id}>
          {m.name}{isDefault ? ' ★' : ''}
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

  const isCurrentDefault = selectedModelId === defaultModelId

  return (
    <div className="flex gap-1 items-center">
      <select
        value={selectedModelId}
        onChange={handleSelectChange}
        className="flex-1 rounded-[8px] border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
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
      <button
        onClick={handleSetDefault}
        disabled={loading || settingDefault || isCurrentDefault || !selectedModelId}
        className={`shrink-0 rounded-[8px] border px-2 py-2 text-sm transition-colors ${
          isCurrentDefault
            ? 'text-yellow-500 border-yellow-500 bg-yellow-50 dark:bg-yellow-950/20'
            : 'text-muted-foreground hover:text-yellow-500 hover:border-yellow-500'
        } disabled:opacity-50 disabled:cursor-not-allowed`}
        title={isCurrentDefault ? 'Current default model' : 'Set as default model'}
      >
        {settingDefault ? '⏳' : '★'}
      </button>
    </div>
  )
}
