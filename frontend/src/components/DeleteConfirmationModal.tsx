import { useState } from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { Button } from './ui/button'

interface DeleteConfirmationModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message: string
  itemsToDelete: Record<string, number>
  warning?: string
  isLoading?: boolean
}

export function DeleteConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  itemsToDelete,
  warning = 'This action cannot be undone.',
  isLoading = false,
}: DeleteConfirmationModalProps) {
  const [acknowledged, setAcknowledged] = useState(false)

  if (!isOpen) return null

  const totalItems = Object.values(itemsToDelete).reduce((a, b) => a + b, 0)

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background rounded-lg p-6 max-w-md w-full mx-4 border shadow-xl">
        <div className="flex items-center gap-3 mb-4">
          <AlertTriangle className="h-6 w-6 text-destructive" />
          <h3 className="text-lg font-semibold">{title}</h3>
        </div>

        <p className="text-sm text-muted-foreground mb-4">{message}</p>

        <div className="bg-muted/50 rounded-lg p-4 mb-4">
          <p className="text-sm font-medium mb-2">The following items will be permanently deleted:</p>
          <ul className="space-y-1">
            {Object.entries(itemsToDelete).map(([key, count]) => (
              <li key={key} className="flex justify-between text-sm">
                <span className="capitalize">{key}</span>
                <span className="font-medium">{count}</span>
              </li>
            ))}
          </ul>
          <p className="text-sm font-medium mt-2 pt-2 border-t">Total: {totalItems}</p>
        </div>

        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-3 mb-4">
          <p className="text-sm text-destructive">{warning}</p>
        </div>

        <label className="flex items-center gap-2 cursor-pointer mb-4">
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(e) => setAcknowledged(e.target.checked)}
            className="h-4 w-4"
          />
          <span className="text-sm">I understand this action is irreversible</span>
        </label>

        <div className="flex justify-end gap-3">
          <Button variant="outline" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={!acknowledged || isLoading}
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Deleting...
              </span>
            ) : (
              'Delete'
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
