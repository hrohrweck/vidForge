import { useEffect, useCallback, useRef } from 'react'

interface UseMediaKeyboardProps {
  selectedAssets: Set<string>
  allAssetIds: string[]
  onSelectAll?: () => void
  onDelete?: () => void
  onRename?: () => void
  onDownload?: () => void
  onNavigate?: (direction: 'up' | 'down' | 'left' | 'right') => void
  onEscape?: () => void
  enabled?: boolean
}

export function useMediaKeyboard({
  selectedAssets,
  allAssetIds,
  onSelectAll,
  onDelete,
  onRename,
  onDownload,
  onNavigate,
  onEscape,
  enabled = true,
}: UseMediaKeyboardProps) {
  const selectedArray = Array.from(selectedAssets)
  const lastSelectedIndex = useRef<number>(-1)

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled) return

      // Cmd/Ctrl + A - Select all
      if ((e.metaKey || e.ctrlKey) && e.key === 'a') {
        e.preventDefault()
        onSelectAll?.()
        return
      }

      // Delete/Backspace - Delete selected
      if (e.key === 'Delete' || e.key === 'Backspace') {
        // Don't trigger if user is typing in an input
        if (
          e.target instanceof HTMLInputElement ||
          e.target instanceof HTMLTextAreaElement
        ) {
          return
        }
        e.preventDefault()
        onDelete?.()
        return
      }

      // F2 - Rename
      if (e.key === 'F2') {
        e.preventDefault()
        onRename?.()
        return
      }

      // Cmd/Ctrl + D - Download
      if ((e.metaKey || e.ctrlKey) && e.key === 'd') {
        e.preventDefault()
        onDownload?.()
        return
      }

      // Escape
      if (e.key === 'Escape') {
        e.preventDefault()
        onEscape?.()
        return
      }

      // Arrow keys - Navigate
      if (onNavigate && ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
        e.preventDefault()
        
        // If nothing selected, select first item
        if (selectedAssets.size === 0 && allAssetIds.length > 0) {
          lastSelectedIndex.current = 0
          return
        }

        // Find index of last selected
        let currentIndex = lastSelectedIndex.current
        if (currentIndex === -1 && selectedArray.length > 0) {
          currentIndex = allAssetIds.indexOf(selectedArray[0])
        }

        if (currentIndex === -1) return

        // Calculate new index based on direction
        // Assuming grid layout: 6 cols on xl, 5 on lg, 4 on md, 3 on sm, 2 on xs
        const cols = window.innerWidth >= 1280 ? 6 :
                     window.innerWidth >= 1024 ? 5 :
                     window.innerWidth >= 768 ? 4 :
                     window.innerWidth >= 640 ? 3 : 2

        let newIndex = currentIndex
        switch (e.key) {
          case 'ArrowLeft':
            newIndex = Math.max(0, currentIndex - 1)
            break
          case 'ArrowRight':
            newIndex = Math.min(allAssetIds.length - 1, currentIndex + 1)
            break
          case 'ArrowUp':
            newIndex = Math.max(0, currentIndex - cols)
            break
          case 'ArrowDown':
            newIndex = Math.min(allAssetIds.length - 1, currentIndex + cols)
            break
        }

        if (newIndex !== currentIndex) {
          lastSelectedIndex.current = newIndex
          // Navigation logic would be handled by parent
        }
      }
    },
    [
      enabled,
      selectedAssets,
      allAssetIds,
      onSelectAll,
      onDelete,
      onRename,
      onDownload,
      onEscape,
      onNavigate,
      selectedArray,
    ]
  )

  useEffect(() => {
    if (!enabled) return

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown, enabled])
}
