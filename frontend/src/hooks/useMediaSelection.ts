import { useState, useCallback, useMemo } from 'react'

export interface UseMediaSelectionReturn {
  /** Set of currently selected media IDs */
  selectedIds: Set<string>
  /** The anchor ID for range selection (last primary selection) */
  anchorId: string | null
  /** Select only this ID (clears all others) */
  selectOnly: (id: string) => void
  /** Toggle selection state of an ID */
  toggle: (id: string) => void
  /** Select a range from anchor to target ID */
  range: (toId: string, orderedIds: string[]) => void
  /** Select all visible items */
  selectAll: (orderedIds: string[]) => void
  /** Clear all selections */
  clear: () => void
  /** Check if an ID is currently selected */
  isSelected: (id: string) => boolean
  /** Count of selected items */
  count: number
}

/**
 * Hook for managing multi-select state for media tiles.
 * Supports single click, cmd/ctrl click, shift click, and select all operations.
 */
export function useMediaSelection(): UseMediaSelectionReturn {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [anchorId, setAnchorId] = useState<string | null>(null)

  const selectOnly = useCallback((id: string) => {
    setSelectedIds(new Set([id]))
    setAnchorId(id)
  }, [])

  const toggle = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
        setAnchorId(id)
      }
      return next
    })
  }, [])

  const range = useCallback((toId: string, orderedIds: string[]) => {
    if (!anchorId) {
      // No anchor, just select the target
      setSelectedIds(new Set([toId]))
      setAnchorId(toId)
      return
    }

    const anchorIndex = orderedIds.indexOf(anchorId)
    const toIndex = orderedIds.indexOf(toId)

    if (anchorIndex === -1 || toIndex === -1) {
      // Anchor or target not in list, fall back to selectOnly
      setSelectedIds(new Set([toId]))
      setAnchorId(toId)
      return
    }

    const start = Math.min(anchorIndex, toIndex)
    const end = Math.max(anchorIndex, toIndex)
    const rangeIds = orderedIds.slice(start, end + 1)

    setSelectedIds(new Set(rangeIds))
    // Anchor stays the same for range operations
  }, [anchorId])

  const selectAll = useCallback((orderedIds: string[]) => {
    setSelectedIds(new Set(orderedIds))
    // Set anchor to last item for consistent range behavior
    if (orderedIds.length > 0) {
      setAnchorId(orderedIds[orderedIds.length - 1])
    }
  }, [])

  const clear = useCallback(() => {
    setSelectedIds(new Set())
    setAnchorId(null)
  }, [])

  const isSelected = useCallback(
    (id: string) => selectedIds.has(id),
    [selectedIds]
  )

  return useMemo(
    () => ({
      selectedIds,
      anchorId,
      selectOnly,
      toggle,
      range,
      selectAll,
      clear,
      isSelected,
      get count() {
        return selectedIds.size
      },
    }),
    [selectedIds, anchorId, selectOnly, toggle, range, selectAll, clear, isSelected]
  )
}
