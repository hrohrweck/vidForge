/**
 * Module-level singleton WebSocket client for real-time media updates.
 *
 * Pattern mirrors `useNotifications.ts`: module-level state + listener Set + emit.
 * Exposes imperative functions (connectMediaWS, disconnectMediaWS)
 * and a React hook (useMediaUpdates) for components.
 */

import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { useAuthStore } from '../stores/auth'
import { mediaKeys } from './useMedia'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Raw WS payload shape (snake_case from Python dispatcher). */
interface MediaEventPayload {
  type: 'media_event'
  event_type: string
  asset_id: string | null
  seq: number
  timestamp: string
}

type MediaListener = (payload: MediaEventPayload) => void

// ---------------------------------------------------------------------------
// Module-level singleton state
// ---------------------------------------------------------------------------

const listeners = new Set<MediaListener>()

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectAttempt = 0
let intentionalClose = false
let lastSeq = 0
let hasFetchedMissed = false

const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function emit(payload: MediaEventPayload): void {
  listeners.forEach((l) => l(payload))
}

/** Derive WebSocket base URL from the current page location. */
function getWsBaseUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

function scheduleReconnect(): void {
  if (intentionalClose) return

  const delay = Math.min(
    RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt),
    RECONNECT_MAX_MS,
  )
  reconnectAttempt++

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    openWebSocket()
  }, delay)
}

function openWebSocket(): void {
  if (ws) {
    ws.onopen = null
    ws.onmessage = null
    ws.onclose = null
    ws.onerror = null
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close()
    }
    ws = null
  }

  const baseUrl = getWsBaseUrl()
  ws = new WebSocket(`${baseUrl}/ws/media`)

  ws.onopen = () => {
    reconnectAttempt = 0
  }

  ws.onmessage = (event: MessageEvent) => {
    try {
      const payload = JSON.parse(event.data as string) as MediaEventPayload
      if (payload.type === 'media_event' && typeof payload.seq === 'number') {
        if (payload.seq > lastSeq) {
          lastSeq = payload.seq
          emit(payload)
        }
      }
    } catch {
      // Ignore malformed messages
    }
  }

  ws.onclose = () => {
    ws = null
    scheduleReconnect()
  }

  ws.onerror = () => {
    // onclose will fire after onerror, so reconnect is handled there
  }
}

// ---------------------------------------------------------------------------
// Public imperative API
// ---------------------------------------------------------------------------

/** Open a WebSocket connection for real-time media updates. */
export function connectMediaWS(): void {
  intentionalClose = false
  reconnectAttempt = 0

  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  openWebSocket()
}

/** Close the WebSocket connection and stop reconnection attempts. */
export function disconnectMediaWS(): void {
  intentionalClose = true

  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  if (ws) {
    ws.onopen = null
    ws.onmessage = null
    ws.onclose = null
    ws.onerror = null
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close()
    }
    ws = null
  }
}

/** Fetch missed media events from the REST API and process them. */
export async function fetchMissedEvents(): Promise<void> {
  try {
    const response = await api.get<MediaEventPayload[]>(`/media/events/since?seq=${lastSeq}`)
    const events = response.data
    for (const payload of events) {
      if (payload.seq > lastSeq) {
        lastSeq = payload.seq
        emit(payload)
      }
    }
  } catch {
    // Silently fail — will rely on WebSocket for future updates
  }
}

// ---------------------------------------------------------------------------
// React hook
// ---------------------------------------------------------------------------

/**
 * React hook that subscribes to media update events.
 *
 * Connects to the WebSocket on mount, fetches missed events,
 * and invalidates the React Query media cache on every event.
 */
export function useMediaUpdates() {
  const queryClient = useQueryClient()
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)

  useEffect(() => {
    if (!isAuthenticated) return

    let cancelled = false

    const listener: MediaListener = () => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.all })
    }
    listeners.add(listener)

    if (!hasFetchedMissed) {
      hasFetchedMissed = true
      fetchMissedEvents().then(() => {
        if (!cancelled) {
          connectMediaWS()
        }
      })
    } else {
      connectMediaWS()
    }

    return () => {
      cancelled = true
      listeners.delete(listener)
    }
  }, [isAuthenticated, queryClient])

  return {
    connected: ws !== null && ws.readyState === WebSocket.OPEN,
  }
}
