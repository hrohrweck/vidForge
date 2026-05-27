import { memo } from 'react'
import { Download, FolderPlus, Tag, Trash2, X } from 'lucide-react'
import { Button } from '../ui/button'
import { useBulkDownload } from '../../hooks/useBulkDownload'
import type { UseMediaSelectionReturn } from '../../hooks/useMediaSelection'

interface BulkActionsBarProps {
  selection: UseMediaSelectionReturn
  onMove: () => void
  onTag: () => void
  onDelete: () => void
}

export const BulkActionsBar = memo(function BulkActionsBar({
  selection,
  onMove,
  onTag,
  onDelete,
}: BulkActionsBarProps) {
  const { isDownloading, error, download, clearError } = useBulkDownload()

  if (selection.count === 0) return null

  const handleDownload = async () => {
    await download(Array.from(selection.selectedIds))
  }

  return (
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-50 w-[70%] animate-in slide-in-from-top-2 duration-300">
      <div className="rounded-xl bg-card border shadow-lg px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-foreground">
            {selection.count} {selection.count === 1 ? 'item' : 'items'} selected
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => selection.clear()}
            className="h-8 px-2 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4 mr-1" />
            Clear
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleDownload} disabled={isDownloading} className="h-9">
            <Download className="h-4 w-4 mr-2" />
            {isDownloading ? 'Downloading…' : 'Download'}
          </Button>
          <Button variant="outline" size="sm" onClick={onMove} className="h-9">
            <FolderPlus className="h-4 w-4 mr-2" />
            Move to…
          </Button>
          <Button variant="outline" size="sm" onClick={onTag} className="h-9">
            <Tag className="h-4 w-4 mr-2" />
            Tag
          </Button>
          <Button variant="destructive" size="sm" onClick={onDelete} className="h-9">
            <Trash2 className="h-4 w-4 mr-2" />
            Delete
          </Button>
        </div>

        {error && (
          <div className="absolute bottom-0 left-0 right-0 translate-y-full pt-1">
            <div className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-1">
              {error}
              <button onClick={clearError} className="ml-2 underline">Dismiss</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
})
