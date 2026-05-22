import { useState, useCallback } from 'react'
import type {
  DragStartEvent,
  DragOverEvent,
  DragEndEvent,
  DragCancelEvent,
  UniqueIdentifier,
} from '@dnd-kit/core'

interface UseFolderDnDProps {
  onMoveAssets?: (assetIds: string[], targetFolderId: string | null) => Promise<void>
  onMoveFolder?: (folderId: string, targetFolderId: string | null) => Promise<void>
}

interface UseFolderDnDReturn {
  activeId: string | null
  overId: string | null
  handleDragStart: (event: DragStartEvent) => void
  handleDragOver: (event: DragOverEvent) => void
  handleDragEnd: (event: DragEndEvent) => void
  handleDragCancel: (event: DragCancelEvent) => void
}

function isAssetId(id: UniqueIdentifier): boolean {
  return String(id).startsWith('asset-')
}

function isFolderId(id: UniqueIdentifier): boolean {
  return String(id).startsWith('folder-')
}

function extractId(id: UniqueIdentifier): string {
  const str = String(id)
  if (str.startsWith('asset-') || str.startsWith('folder-')) {
    return str.slice(6)
  }
  return str
}

export function useFolderDnD({
  onMoveAssets,
  onMoveFolder,
}: UseFolderDnDProps): UseFolderDnDReturn {
  const [activeId, setActiveId] = useState<string | null>(null)
  const [overId, setOverId] = useState<string | null>(null)

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveId(String(event.active.id))
  }, [])

  const handleDragOver = useCallback((event: DragOverEvent) => {
    setOverId(event.over?.id ? String(event.over.id) : null)
  }, [])

  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      const { active, over } = event

      if (!over) {
        setActiveId(null)
        setOverId(null)
        return
      }

      const targetId = String(over.id)
      const activeIdStr = String(active.id)

      // Check if we're dropping on a folder
      if (isFolderId(targetId)) {
        const targetFolderId = extractId(targetId)

        // If active is an asset
        if (isAssetId(activeIdStr)) {
          const assetId = extractId(activeIdStr)
          await onMoveAssets?.([assetId], targetFolderId)
        }
        // If active is a folder (and not the same folder)
        else if (isFolderId(activeIdStr) && activeIdStr !== targetId) {
          const folderId = extractId(activeIdStr)
          await onMoveFolder?.(folderId, targetFolderId)
        }
      }
      // If dropping on "root" or no folder
      else if (targetId === 'root' || targetId === 'all-assets') {
        if (isAssetId(activeIdStr)) {
          const assetId = extractId(activeIdStr)
          await onMoveAssets?.([assetId], null)
        } else if (isFolderId(activeIdStr)) {
          const folderId = extractId(activeIdStr)
          await onMoveFolder?.(folderId, null)
        }
      }

      setActiveId(null)
      setOverId(null)
    },
    [onMoveAssets, onMoveFolder]
  )

  const handleDragCancel = useCallback(() => {
    setActiveId(null)
    setOverId(null)
  }, [])

  return {
    activeId,
    overId,
    handleDragStart,
    handleDragOver,
    handleDragEnd,
    handleDragCancel,
  }
}
