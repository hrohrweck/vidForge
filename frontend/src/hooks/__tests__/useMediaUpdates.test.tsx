import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest'
import React from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'

describe('useMediaUpdates', () => {
  interface MockWSInstance {
    url: string
    send: ReturnType<typeof vi.fn>
    close: ReturnType<typeof vi.fn>
    readyState: number
    onopen: ((ev: Event) => void) | null
    onmessage: ((ev: MessageEvent) => void) | null
    onclose: ((ev: CloseEvent) => void) | null
    onerror: ((ev: Event) => void) | null
  }

  let MockWebSocket: Mock<[url: string], MockWSInstance>
  let wsInstances: MockWSInstance[]
  let originalWebSocket: typeof WebSocket

  beforeEach(() => {
    vi.resetModules()
    wsInstances = []
    originalWebSocket = global.WebSocket

    MockWebSocket = vi.fn(function (this: MockWSInstance, url: string) {
      const instance: MockWSInstance = {
        url,
        send: vi.fn(),
        close: vi.fn(),
        readyState: WebSocket.CONNECTING,
        onopen: null,
        onmessage: null,
        onclose: null,
        onerror: null,
      }
      wsInstances.push(instance)
      return instance
    })

    vi.stubGlobal('WebSocket', MockWebSocket)
    if (typeof window !== 'undefined') {
      window.localStorage.clear()
    }

    server.use(
      http.get('*/api/media/events/since', () => {
        return HttpResponse.json([])
      })
    )
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.stubGlobal('WebSocket', originalWebSocket)
  })

  it('opens WebSocket on mount when authenticated', async () => {
    const { useAuthStore } = await import('../../stores/auth')
    useAuthStore.setState({ isAuthenticated: true, user: { id: 'u1', email: 'a@b.com', is_active: true, is_superuser: false, groups: [], permissions: [] } })

    const { useMediaUpdates } = await import('../useMediaUpdates')
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    renderHook(() => useMediaUpdates(), { wrapper })

    await waitFor(() => {
      expect(MockWebSocket).toHaveBeenCalledTimes(1)
    })

    const instance = wsInstances[0]
    expect(instance.url).toBe('ws://localhost:3000/ws/media')
  })

  it('invalidates queries on media_event', async () => {
    const { useAuthStore } = await import('../../stores/auth')
    useAuthStore.setState({ isAuthenticated: true, user: { id: 'u1', email: 'a@b.com', is_active: true, is_superuser: false, groups: [], permissions: [] } })

    const { useMediaUpdates } = await import('../useMediaUpdates')
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    renderHook(() => useMediaUpdates(), { wrapper })

    await waitFor(() => {
      expect(wsInstances.length).toBeGreaterThan(0)
    })

    const instance = wsInstances[0]
    instance.readyState = WebSocket.OPEN
    if (instance.onopen) instance.onopen(new Event('open'))

    const payload = {
      type: 'media_event',
      event_type: 'created',
      asset_id: 'asset-1',
      seq: 1,
      timestamp: '2024-01-01T00:00:00Z',
    }

    if (instance.onmessage) {
      instance.onmessage(new MessageEvent('message', { data: JSON.stringify(payload) }))
    }

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['media'] })
    })
  })

  it('ignores non-media events', async () => {
    const { useAuthStore } = await import('../../stores/auth')
    useAuthStore.setState({ isAuthenticated: true, user: { id: 'u1', email: 'a@b.com', is_active: true, is_superuser: false, groups: [], permissions: [] } })

    const { useMediaUpdates } = await import('../useMediaUpdates')
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    renderHook(() => useMediaUpdates(), { wrapper })

    await waitFor(() => {
      expect(wsInstances.length).toBeGreaterThan(0)
    })

    const instance = wsInstances[0]
    instance.readyState = WebSocket.OPEN
    if (instance.onopen) instance.onopen(new Event('open'))

    const payload = {
      type: 'error_event',
      event_type: 'error',
      asset_id: null,
      seq: 1,
      timestamp: '2024-01-01T00:00:00Z',
    }

    if (instance.onmessage) {
      instance.onmessage(new MessageEvent('message', { data: JSON.stringify(payload) }))
    }

    expect(invalidateSpy).not.toHaveBeenCalled()
  })

  it('reconnects after disconnect', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })

    const { useAuthStore } = await import('../../stores/auth')
    useAuthStore.setState({ isAuthenticated: true, user: { id: 'u1', email: 'a@b.com', is_active: true, is_superuser: false, groups: [], permissions: [] } })

    const { useMediaUpdates } = await import('../useMediaUpdates')
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    renderHook(() => useMediaUpdates(), { wrapper })

    await waitFor(() => {
      expect(wsInstances.length).toBe(1)
    })

    const instance = wsInstances[0]
    if (instance.onclose) {
      instance.onclose(new Event('close') as unknown as CloseEvent)
    }

    vi.advanceTimersByTime(1000)

    await waitFor(() => {
      expect(MockWebSocket).toHaveBeenCalledTimes(2)
    })
  })

  it('fetches missed events on mount', async () => {
    const fetchSpy = vi.fn()

    server.use(
      http.get('*/api/media/events/since', ({ request }) => {
        fetchSpy(request.url)
        return HttpResponse.json([
          {
            type: 'media_event',
            event_type: 'created',
            asset_id: 'asset-1',
            seq: 1,
            timestamp: '2024-01-01T00:00:00Z',
          },
        ])
      })
    )

    const { useAuthStore } = await import('../../stores/auth')
    useAuthStore.setState({ isAuthenticated: true, user: { id: 'u1', email: 'a@b.com', is_active: true, is_superuser: false, groups: [], permissions: [] } })

    const { useMediaUpdates } = await import('../useMediaUpdates')
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    renderHook(() => useMediaUpdates(), { wrapper })

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled()
    })

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/media/events/since')
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('seq=0')
    )

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['media'] })
    })
  })

  it('skips stale events by seq', async () => {
    const { useAuthStore } = await import('../../stores/auth')
    useAuthStore.setState({ isAuthenticated: true, user: { id: 'u1', email: 'a@b.com', is_active: true, is_superuser: false, groups: [], permissions: [] } })

    const { useMediaUpdates } = await import('../useMediaUpdates')
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    renderHook(() => useMediaUpdates(), { wrapper })

    await waitFor(() => {
      expect(wsInstances.length).toBeGreaterThan(0)
    })

    const instance = wsInstances[0]
    instance.readyState = WebSocket.OPEN
    if (instance.onopen) instance.onopen(new Event('open'))

    const payload1 = {
      type: 'media_event',
      event_type: 'created',
      asset_id: 'asset-1',
      seq: 5,
      timestamp: '2024-01-01T00:00:00Z',
    }

    if (instance.onmessage) {
      instance.onmessage(new MessageEvent('message', { data: JSON.stringify(payload1) }))
    }

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledTimes(1)
    })

    const payload2 = {
      type: 'media_event',
      event_type: 'updated',
      asset_id: 'asset-2',
      seq: 3,
      timestamp: '2024-01-01T00:00:00Z',
    }

    if (instance.onmessage) {
      instance.onmessage(new MessageEvent('message', { data: JSON.stringify(payload2) }))
    }

    expect(invalidateSpy).toHaveBeenCalledTimes(1)
  })
})
