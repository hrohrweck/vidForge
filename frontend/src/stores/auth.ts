import { create } from 'zustand'
import { persist } from 'zustand/middleware'

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
  token: string | null
  user: User | null
  isAuthenticated: boolean
  setAuth: (token: string, user: User) => void
  logout: () => void
  hasPermission: (permission: string) => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      setAuth: (token, user) =>
        set({
          token,
          user,
          isAuthenticated: true,
        }),
      logout: () =>
        set({
          token: null,
          user: null,
          isAuthenticated: false,
        }),
      hasPermission: (permission: string) => {
        const user = get().user
        if (!user) return false
        if (user.is_superuser) return true
        return user.permissions.includes(permission)
      },
    }),
    {
      name: 'auth-storage',
    }
  )
)
