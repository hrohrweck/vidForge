import { memo } from 'react'
import { Download, FolderPlus, Tag, Trash2, X } from 'lucide-react'
import { Button } from '../ui/button'
import { useBulkDownload } from '../../hooks/useBulkDownload'
import type { UseMediaSelectionReturn } from '../../hooks/useMediaSelection'

interface BulkActionsBarProps {
  /** Selection state from useMediaSelection hook */
  selection: UseMediaSelectionReturn
  /** Callback when Move to… button is clicked */
  onMove: () => void
  /** Callback when Tag button is clicked */
  onTag: () => void
  /** Callback when Delete button is clicked */
  onDelete: () => void
}

/**
 * Sticky bottom action bar that appears when items are selected.
 * Provides bulk operations: Download, Move, Tag, Delete, and Clear selection.
 */
export const BulkActionsBar = memo(function BulkActionsBar({
  selection,
  onMove,
  onTag,
  onDelete,
}: BulkActionsBarProps) {
  const { isDownloading, error, download, clearError } = useBulkDownload()

  // Don't render if nothing selected
  if (selection.count === 0) {
    return null
  }

  const handleDownload = async () => {
    const assetIds = Array.from(selection.selectedIds)
    await download(assetIds)
  }

  const handleClear = () => {
    selection.clear()
  }

  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-50 bg-card border-t border-border shadow-lg transition-transform duration-300 ease-in-out"
      style={{
        transform: selection.count > 0 ? 'translateY(0)' : 'translateY(100%)',
      }}
    >
      <div className="max-w-7xl mx-auto px-4 py-3">
        <div className="flex items-center justify-between gap-4">
          {/* Selection count */}
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-foreground">
              {selection.count} {selection.count === 1 ? 'item' : 'items'} selected
            </span>
            
            {/* Clear button */}
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClear}
              className="h-8 px-2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4 mr-1" />
              Clear
            </Button>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            {/* Download button */}
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownload}
              disabled={isDownloading}
              className="h-9"
            >
              <Download className="h-4 w-4 mr-2" />
              {isDownloading ? 'Downloading…' : 'Download'}
            </Button>

            {/* Move to… button */}
            <Button
              variant="outline"
              size="sm"
              onClick={onMove}
              className="h-9"
            >
              <FolderPlus className="h-4 w-4 mr-2" />
              Move to…
            </Button>

            {/* Tag button */}
            <Button
              variant="outline"
              size="sm"
              onClick={onTag}
              className="h-9"
            >
              <Tag className="h-4 w-4 mr-2" />
              Tag
            </Button>

            {/* Delete button */}
            <Button
              variant="destructive"
              size="sm"
              onClick={onDelete}
              className="h-9"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Delete
            </Button>
          </div>
        </div>

        {/* Error message */}
        {error && (
          <div className="mt-2 text-sm text-destructive">
            {error}
            <button
              onClick={clearError}
              className="ml-2 underline hover:text-destructive/80"
            >
              Dismiss
            </button>
          </div>
        )}
      </div>
    </div>
  )
})
