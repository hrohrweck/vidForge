import { useState } from 'react'
import { X, Plus } from 'lucide-react'
import { useTags, useCreateTag } from '../../hooks/useMedia'
import type { MediaTag } from '../../api/types/media'

interface TagPickerProps {
  selectedTags: MediaTag[]
  onChange: (tags: MediaTag[]) => void
}

const TAG_COLORS = [
  'ef4444', 'f97316', 'f59e0b', '84cc16', '22c55e',
  '14b8a6', '06b6d4', '3b82f6', '6366f1', '8b5cf6',
  'a855f7', 'ec4899',
]

export function TagPicker({ selectedTags, onChange }: TagPickerProps) {
  const [isCreating, setIsCreating] = useState(false)
  const [newTagName, setNewTagName] = useState('')
  const [selectedColor, setSelectedColor] = useState(TAG_COLORS[0])
  
  const { data: availableTags } = useTags()
  const createTag = useCreateTag()

  const toggleTag = (tag: MediaTag) => {
    const exists = selectedTags.find((t) => t.id === tag.id)
    if (exists) {
      onChange(selectedTags.filter((t) => t.id !== tag.id))
    } else {
      onChange([...selectedTags, tag])
    }
  }

  const handleCreateTag = () => {
    if (!newTagName.trim()) return
    
    createTag.mutate(
      { name: newTagName.trim(), color: selectedColor },
      {
        onSuccess: (newTag) => {
          onChange([...selectedTags, newTag])
          setNewTagName('')
          setIsCreating(false)
        },
      }
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {selectedTags.map((tag) => (
          <span
            key={tag.id}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs text-white"
            style={{ backgroundColor: `#${tag.color}` }}
          >
            {tag.name}
            <button
              onClick={() => toggleTag(tag)}
              className="hover:bg-white/20 rounded-full p-0.5"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
      </div>

      {availableTags && availableTags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {availableTags
            .filter((tag) => !selectedTags.find((t) => t.id === tag.id))
            .map((tag) => (
              <button
                key={tag.id}
                onClick={() => toggleTag(tag)}
                className="px-2 py-1 rounded-full text-xs border hover:bg-muted/50"
                style={{ borderColor: `#${tag.color}`, color: `#${tag.color}` }}
              >
                + {tag.name}
              </button>
            ))}
        </div>
      )}

      {isCreating ? (
        <div className="flex items-center gap-2 p-2 border rounded-lg">
          <input
            type="text"
            value={newTagName}
            onChange={(e) => setNewTagName(e.target.value)}
            placeholder="Tag name"
            className="flex-1 px-2 py-1 border rounded text-sm"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCreateTag()
              if (e.key === 'Escape') setIsCreating(false)
            }}
          />
          <div className="flex gap-1">
            {TAG_COLORS.map((color) => (
              <button
                key={color}
                onClick={() => setSelectedColor(color)}
                className={`w-5 h-5 rounded-full ${
                  selectedColor === color ? 'ring-2 ring-offset-1 ring-muted-foreground' : ''
                }`}
                style={{ backgroundColor: `#${color}` }}
              />
            ))}
          </div>
          <button
            onClick={handleCreateTag}
            disabled={!newTagName.trim() || createTag.isPending}
            className="px-3 py-1 bg-primary text-primary-foreground rounded text-sm hover:bg-primary/90 disabled:opacity-50"
          >
            Create
          </button>
        </div>
      ) : (
        <button
          onClick={() => setIsCreating(true)}
          className="flex items-center gap-1 text-sm text-primary hover:text-primary/80"
        >
          <Plus className="h-4 w-4" />
          Create new tag
        </button>
      )}
    </div>
  )
}
