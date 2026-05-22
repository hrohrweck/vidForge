import { useState, useEffect, useCallback, useRef } from 'react'

export interface RenameDialogProps {
  name: string
  onRename: (newName: string) => void | Promise<void>
  onCancel: () => void
}

/**
 * Inline rename input component used by MediaTile and FolderRail.
 * Replaces a text label with an editable input field.
 * 
 * - Enter: commit (validates non-empty, strips whitespace)
 * - Escape: cancel
 * - Blur: commit if name changed and non-empty
 */
export function RenameDialog({ name, onRename, onCancel }: RenameDialogProps) {
  const [editName, setEditName] = useState(name)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Focus and select-all on mount
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [])

  const validateName = (value: string): string | null => {
    const trimmed = value.trim()
    if (!trimmed) {
      return 'Name cannot be empty'
    }
    return null
  }

  const handleSubmit = useCallback(async () => {
    const trimmed = editName.trim()
    const validationError = validateName(editName)
    
    if (validationError) {
      setError(validationError)
      return
    }

    if (trimmed === name) {
      // No change, just cancel
      onCancel()
      return
    }

    try {
      setIsSaving(true)
      setError(null)
      await onRename(trimmed)
      onCancel()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rename')
      setIsSaving(false)
    }
  }, [editName, name, onRename, onCancel])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleSubmit()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      onCancel()
    }
  }, [handleSubmit, onCancel])

  const handleBlur = useCallback(() => {
    // Delay to allow click events to propagate
    setTimeout(() => {
      const trimmed = editName.trim()
      if (trimmed && trimmed !== name) {
        handleSubmit()
      } else {
        onCancel()
      }
    }, 150)
  }, [editName, name, handleSubmit, onCancel])

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setEditName(e.target.value)
    // Clear error when user starts typing
    if (error) {
      setError(null)
    }
  }, [error])

  return (
    <div className="flex flex-col gap-1">
      <input
        ref={inputRef}
        type="text"
        value={editName}
        onChange={handleChange}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        disabled={isSaving}
        className={`w-full bg-white/90 text-foreground text-sm px-2 py-1 rounded border-b-2 focus:outline-none focus:border-primary transition-colors ${
          error ? 'border-destructive' : 'border-border'
        } ${isSaving ? 'opacity-50 cursor-not-allowed' : ''}`}
        onClick={(e) => e.stopPropagation()}
      />
      {error && (
        <p className="text-xs text-destructive px-1">{error}</p>
      )}
    </div>
  )
}
