import { useEffect, useRef } from 'react'
import {
  Download,
  Trash2,
  Tag,
  FileEdit,
  Copy,
  ExternalLink,
  Film,
} from 'lucide-react'
import type { MediaAsset } from '../../api/types/media'

interface ContextMenuPosition {
  x: number
  y: number
}

interface MediaContextMenuProps {
  asset: MediaAsset | null
  position: ContextMenuPosition | null
  isOpen: boolean
  onClose: () => void
  onRename?: (asset: MediaAsset) => void
  onDelete?: (asset: MediaAsset) => void
  onDownload?: (asset: MediaAsset) => void
  onTag?: (asset: MediaAsset) => void
  onUseInProject?: (asset: MediaAsset) => void
  onOpenInNewTab?: (asset: MediaAsset) => void
  onCopyUrl?: (asset: MediaAsset) => void
}

export function MediaContextMenu({
  asset,
  position,
  isOpen,
  onClose,
  onRename,
  onDelete,
  onDownload,
  onTag,
  onUseInProject,
  onOpenInNewTab,
  onCopyUrl,
}: MediaContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return

    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose()
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen, onClose])

  // Close on escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])

  if (!isOpen || !position || !asset) return null

  // Ensure menu stays within viewport
  const menuX = Math.min(position.x, window.innerWidth - 220)
  const menuY = Math.min(position.y, window.innerHeight - 300)

  const handleAction = (callback?: (asset: MediaAsset) => void) => {
    if (callback) {
      callback(asset)
    }
    onClose()
  }

  return (
    <div
      ref={menuRef}
      className="fixed z-50 w-56 bg-card border border-border rounded-lg shadow-lg py-1"
      style={{
        left: menuX,
        top: menuY,
      }}
    >
      {onRename && (
        <button
          onClick={() => handleAction(onRename)}
          className="w-full px-4 py-2 text-left text-sm hover:bg-muted flex items-center gap-2"
        >
          <FileEdit className="w-4 h-4" />
          Rename
        </button>
      )}

      {onTag && (
        <button
          onClick={() => handleAction(onTag)}
          className="w-full px-4 py-2 text-left text-sm hover:bg-muted flex items-center gap-2"
        >
          <Tag className="w-4 h-4" />
          Add Tags
        </button>
      )}

      {onUseInProject && (
        <button
          onClick={() => handleAction(onUseInProject)}
          className="w-full px-4 py-2 text-left text-sm hover:bg-muted flex items-center gap-2"
        >
          <Film className="w-4 h-4" />
          Use in Project
        </button>
      )}

      <div className="border-t border-border my-1" />

      {onDownload && (
        <button
          onClick={() => handleAction(onDownload)}
          className="w-full px-4 py-2 text-left text-sm hover:bg-muted flex items-center gap-2"
        >
          <Download className="w-4 h-4" />
          Download
        </button>
      )}

      {onCopyUrl && (
        <button
          onClick={() => handleAction(onCopyUrl)}
          className="w-full px-4 py-2 text-left text-sm hover:bg-muted flex items-center gap-2"
        >
          <Copy className="w-4 h-4" />
          Copy URL
        </button>
      )}

      {onOpenInNewTab && (
        <button
          onClick={() => handleAction(onOpenInNewTab)}
          className="w-full px-4 py-2 text-left text-sm hover:bg-muted flex items-center gap-2"
        >
          <ExternalLink className="w-4 h-4" />
          Open in New Tab
        </button>
      )}

      <div className="border-t border-border my-1" />

      {onDelete && (
        <button
          onClick={() => handleAction(onDelete)}
          className="w-full px-4 py-2 text-left text-sm hover:bg-destructive hover:text-destructive-foreground flex items-center gap-2 text-destructive"
        >
          <Trash2 className="w-4 h-4" />
          Delete
        </button>
      )}
    </div>
  )
}
