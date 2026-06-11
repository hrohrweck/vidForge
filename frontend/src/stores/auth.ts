import { create } from 'zustand'
import { useUiStore } from './ui'

interface Group {
  id: string
  name: string
  description?: string
}

interface User {
  id: string
  email: string
  is_active: boolean
  is_superuser: boolean
  groups: Group[]
  permissions: string[]
}

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  setAuth: (user: User) => void
  logout: () => void
  hasPermission: (permission: string) => boolean
}

export const useAuthStore = create<AuthState>()((set, get) => ({
  user: null,
  isAuthenticated: false,
  setAuth: (user) =>
    set({
      user,
      isAuthenticated: true,
    }),
  logout: () => {
    fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    set({
      user: null,
      isAuthenticated: false,
    })
    useUiStore.getState().resetUiPreferences()
  },
  hasPermission: (permission: string) => {
    const user = get().user
    if (!user) return false
    if (user.is_superuser) return true
    return user.permissions.includes(permission)
  },
}))
