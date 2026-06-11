import { create } from 'zustand'
import { usersApi } from '../api/client'

interface UiState {
  isSidebarOpen: boolean
  sidebarHydrated: boolean
  sidebarError: string | null
  hydrateSidebarPreference: () => Promise<void>
  setSidebarOpen: (next: boolean) => void
  toggleSidebar: () => void
  resetUiPreferences: () => void
}

let sidebarSaveVersion = 0

export const useUiStore = create<UiState>()((set) => ({
  isSidebarOpen: true,
  sidebarHydrated: false,
  sidebarError: null,

  hydrateSidebarPreference: async () => {
    try {
      const data = await usersApi.getSidebarPreference()
      set({
        isSidebarOpen: data.sidebar_open,
        sidebarHydrated: true,
        sidebarError: null,
      })
    } catch {
      // Default to open on non-auth failures
      set({
        isSidebarOpen: true,
        sidebarHydrated: true,
        sidebarError: null,
      })
    }
  },

  setSidebarOpen: (next) => {
    const previous = useUiStore.getState().isSidebarOpen
    if (next === previous) return

    set({ isSidebarOpen: next, sidebarError: null })

    sidebarSaveVersion += 1
    const thisVersion = sidebarSaveVersion

    usersApi
      .setSidebarPreference(next)
      .catch(() => {
        // Only revert if this is still the latest save request
        if (thisVersion === sidebarSaveVersion) {
          set({ isSidebarOpen: previous, sidebarError: 'Failed to save sidebar preference' })
        }
      })
  },

  toggleSidebar: () => {
    set((state) => {
      const next = !state.isSidebarOpen
      setTimeout(() => {
        useUiStore.getState().setSidebarOpen(next)
      }, 0)
      return { isSidebarOpen: next, sidebarError: null }
    })
  },

  resetUiPreferences: () => {
    set({
      isSidebarOpen: true,
      sidebarHydrated: false,
      sidebarError: null,
    })
  },
}))
