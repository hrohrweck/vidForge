import { useChatStore } from '../../stores/chat'

const MODELS = [
  { id: 'qwen3.6:14b', label: 'Qwen 3.6 14B' },
  { id: 'llama3.3:70b', label: 'Llama 3.3 70B' },
  { id: 'qwen3.6:35b', label: 'Qwen 3.6 35B' },
]

export function ModelPicker() {
  const selectedModelId = useChatStore((s) => s.selectedModelId)
  const setModel = useChatStore((s) => s.setModel)

  return (
    <select
      value={selectedModelId}
      onChange={(e) => setModel(e.target.value)}
      className="w-full rounded-md border px-3 py-2 text-sm"
    >
      {MODELS.map((m) => (
        <option key={m.id} value={m.id}>
          {m.label}
        </option>
      ))}
    </select>
  )
}