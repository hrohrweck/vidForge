import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useMediaSelection } from '../useMediaSelection'

describe('useMediaSelection', () => {
  const orderedIds = ['id1', 'id2', 'id3', 'id4', 'id5']

  describe('selectOnly', () => {
    it('clears all and selects one, sets anchor', () => {
      const { result } = renderHook(() => useMediaSelection())

      act(() => {
        result.current.selectOnly('id3')
      })

      expect(result.current.selectedIds).toEqual(new Set(['id3']))
      expect(result.current.anchorId).toBe('id3')
      expect(result.current.count).toBe(1)
      expect(result.current.isSelected('id3')).toBe(true)
      expect(result.current.isSelected('id1')).toBe(false)
    })

    it('replaces previous selection when called again', () => {
      const { result } = renderHook(() => useMediaSelection())

      act(() => {
        result.current.selectOnly('id1')
      })

      act(() => {
        result.current.selectOnly('id5')
      })

      expect(result.current.selectedIds).toEqual(new Set(['id5']))
      expect(result.current.anchorId).toBe('id5')
      expect(result.current.count).toBe(1)
    })
  })

  describe('toggle', () => {
    it('adds item to selection and sets anchor when not selected', () => {
      const { result } = renderHook(() => useMediaSelection())

      act(() => {
        result.current.toggle('id2')
      })

      expect(result.current.selectedIds).toEqual(new Set(['id2']))
      expect(result.current.anchorId).toBe('id2')
      expect(result.current.count).toBe(1)
    })

    it('removes item from selection when already selected', () => {
      const { result } = renderHook(() => useMediaSelection())

      act(() => {
        result.current.toggle('id2')
      })

      act(() => {
        result.current.toggle('id2')
      })

      expect(result.current.selectedIds).toEqual(new Set([]))
      expect(result.current.anchorId).toBe('id2') // anchor stays
      expect(result.current.count).toBe(0)
    })

    it('preserves other items when toggling one off', () => {
      const { result } = renderHook(() => useMediaSelection())

      act(() => {
        result.current.toggle('id1')
        result.current.toggle('id2')
        result.current.toggle('id3')
      })

      expect(result.current.count).toBe(3)

      act(() => {
        result.current.toggle('id2')
      })

      expect(result.current.selectedIds).toEqual(new Set(['id1', 'id3']))
      expect(result.current.count).toBe(2)
    })
  })

  describe('range', () => {
    it('selects range from anchor to target (forward)', () => {
      const { result } = renderHook(() => useMediaSelection())

      // Set anchor
      act(() => {
        result.current.selectOnly('id2')
      })

      // Select range to id4
      act(() => {
        result.current.range('id4', orderedIds)
      })

      expect(result.current.selectedIds).toEqual(new Set(['id2', 'id3', 'id4']))
      expect(result.current.anchorId).toBe('id2') // anchor unchanged
      expect(result.current.count).toBe(3)
    })

    it('selects range from anchor to target (backward)', () => {
      const { result } = renderHook(() => useMediaSelection())

      // Set anchor at id4
      act(() => {
        result.current.selectOnly('id4')
      })

      // Select range back to id2
      act(() => {
        result.current.range('id2', orderedIds)
      })

      expect(result.current.selectedIds).toEqual(new Set(['id2', 'id3', 'id4']))
      expect(result.current.anchorId).toBe('id4') // anchor unchanged
      expect(result.current.count).toBe(3)
    })

    it('handles missing anchor by selecting only target', () => {
      const { result } = renderHook(() => useMediaSelection())

      // No anchor set, call range directly
      act(() => {
        result.current.range('id3', orderedIds)
      })

      expect(result.current.selectedIds).toEqual(new Set(['id3']))
      expect(result.current.anchorId).toBe('id3')
    })

    it('handles missing anchor or target in orderedIds', () => {
      const { result } = renderHook(() => useMediaSelection())

      act(() => {
        result.current.selectOnly('id1')
      })

      // Target not in list
      act(() => {
        result.current.range('nonexistent', orderedIds)
      })

      expect(result.current.selectedIds).toEqual(new Set(['nonexistent']))
      expect(result.current.anchorId).toBe('nonexistent')
    })
  })

  describe('selectAll', () => {
    it('selects all items and sets anchor to last', () => {
      const { result } = renderHook(() => useMediaSelection())

      act(() => {
        result.current.selectAll(orderedIds)
      })

      expect(result.current.selectedIds).toEqual(new Set(orderedIds))
      expect(result.current.anchorId).toBe('id5') // last item
      expect(result.current.count).toBe(5)
    })

    it('handles empty list', () => {
      const { result } = renderHook(() => useMediaSelection())

      act(() => {
        result.current.selectAll([])
      })

      expect(result.current.selectedIds).toEqual(new Set([]))
      expect(result.current.anchorId).toBe(null)
      expect(result.current.count).toBe(0)
    })
  })

  describe('clear', () => {
    it('clears all selections and resets anchor', () => {
      const { result } = renderHook(() => useMediaSelection())

      act(() => {
        result.current.toggle('id1')
        result.current.toggle('id2')
        result.current.toggle('id3')
      })

      expect(result.current.count).toBe(3)

      act(() => {
        result.current.clear()
      })

      expect(result.current.selectedIds).toEqual(new Set([]))
      expect(result.current.anchorId).toBe(null)
      expect(result.current.count).toBe(0)
    })
  })

  describe('isSelected', () => {
    it('returns true for selected items', () => {
      const { result } = renderHook(() => useMediaSelection())

      act(() => {
        result.current.toggle('id1')
        result.current.toggle('id3')
      })

      expect(result.current.isSelected('id1')).toBe(true)
      expect(result.current.isSelected('id3')).toBe(true)
      expect(result.current.isSelected('id2')).toBe(false)
      expect(result.current.isSelected('id5')).toBe(false)
    })
  })

  describe('count', () => {
    it('returns correct count of selected items', () => {
      const { result } = renderHook(() => useMediaSelection())

      expect(result.current.count).toBe(0)

      act(() => {
        result.current.toggle('id1')
      })
      expect(result.current.count).toBe(1)

      act(() => {
        result.current.toggle('id2')
      })
      expect(result.current.count).toBe(2)

      act(() => {
        result.current.toggle('id1')
      })
      expect(result.current.count).toBe(1)

      act(() => {
        result.current.clear()
      })
      expect(result.current.count).toBe(0)
    })
  })
})
