import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAuthStore } from '../../stores/auth'

describe('AuthStore', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })

  it('does not write token to localStorage on login', () => {
    const setItemSpy = vi.spyOn(window.localStorage, 'setItem')

    useAuthStore.getState().setAuth({
      id: '1',
      email: 'test@example.com',
      is_active: true,
      is_superuser: false,
      groups: [],
      permissions: [],
    })

    const tokenWrites = setItemSpy.mock.calls.filter(
      ([key]) =>
        typeof key === 'string' &&
        (key.toLowerCase().includes('token') || key.toLowerCase().includes('auth'))
    )

    expect(tokenWrites).toHaveLength(0)
    setItemSpy.mockRestore()
  })
})
