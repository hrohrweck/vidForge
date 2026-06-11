import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useUiStore } from '../../stores/ui'
import { usersApi } from '../../api/client'

vi.mock('../../api/client', () => ({
  usersApi: {
    getSidebarPreference: vi.fn(),
    setSidebarPreference: vi.fn(),
  },
}))

describe('useUiStore', () => {
  beforeEach(() => {
    useUiStore.setState({
      isSidebarOpen: true,
      sidebarHydrated: false,
      sidebarError: null,
    })
    vi.clearAllMocks()
  })

  it('default state is open and not hydrated', () => {
    const state = useUiStore.getState()
    expect(state.isSidebarOpen).toBe(true)
    expect(state.sidebarHydrated).toBe(false)
    expect(state.sidebarError).toBeNull()
  })

  it('hydrate maps backend sidebar_open: false to collapsed state and hydrated true', async () => {
    vi.mocked(usersApi.getSidebarPreference).mockResolvedValueOnce({ sidebar_open: false })

    await useUiStore.getState().hydrateSidebarPreference()

    const state = useUiStore.getState()
    expect(state.isSidebarOpen).toBe(false)
    expect(state.sidebarHydrated).toBe(true)
    expect(state.sidebarError).toBeNull()
  })

  it('hydrate failure defaults open and hydrated true', async () => {
    vi.mocked(usersApi.getSidebarPreference).mockRejectedValueOnce(new Error('network error'))

    await useUiStore.getState().hydrateSidebarPreference()

    const state = useUiStore.getState()
    expect(state.isSidebarOpen).toBe(true)
    expect(state.sidebarHydrated).toBe(true)
    expect(state.sidebarError).toBeNull()
  })

  it('setSidebarOpen(false) calls usersApi.setSidebarPreference(false) and updates state', async () => {
    vi.mocked(usersApi.setSidebarPreference).mockResolvedValueOnce({ sidebar_open: false })

    useUiStore.getState().setSidebarOpen(false)

    expect(useUiStore.getState().isSidebarOpen).toBe(false)
    expect(usersApi.setSidebarPreference).toHaveBeenCalledWith(false)

    // Wait for async
    await vi.waitFor(() => expect(usersApi.setSidebarPreference).toHaveBeenCalled())
  })

  it('failed save reverts to previous state only for the latest request (race guard)', async () => {
    // First toggle: open -> closed (will fail)
    const error1 = new Error('fail1')
    vi.mocked(usersApi.setSidebarPreference).mockRejectedValueOnce(error1)

    // Second toggle: closed -> open (will succeed)
    vi.mocked(usersApi.setSidebarPreference).mockResolvedValueOnce({ sidebar_open: true })

    useUiStore.getState().setSidebarOpen(false)
    expect(useUiStore.getState().isSidebarOpen).toBe(false)

    // Immediately toggle back before first request resolves
    useUiStore.getState().setSidebarOpen(true)
    expect(useUiStore.getState().isSidebarOpen).toBe(true)

    // Wait for both async calls to settle
    await vi.waitFor(() =>
      expect(usersApi.setSidebarPreference).toHaveBeenCalledTimes(2)
    )

    // Because the second request was the latest, the first failure should NOT revert state
    const state = useUiStore.getState()
    expect(state.isSidebarOpen).toBe(true)
    expect(state.sidebarError).toBeNull()
  })
})
