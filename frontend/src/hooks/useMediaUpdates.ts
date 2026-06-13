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
import { PersistentWebSocket } from '../lib/websocket'
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

let ws: PersistentWebSocket | null = null
let lastSeq = 0
let hasFetchedMissed = false

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

function openWebSocket(): void {
  if (ws) {
    ws.disconnect()
    ws = null
  }

  const baseUrl = getWsBaseUrl()
  ws = new PersistentWebSocket({
    url: `${baseUrl}/ws/media`,
    authRetry: true,
    onMessage: (event: MessageEvent) => {
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
    },
  })
  ws.connect()
}

// ---------------------------------------------------------------------------
// Public imperative API
// ---------------------------------------------------------------------------

/** Open a WebSocket connection for real-time media updates. */
export function connectMediaWS(): void {
  if (ws?.connected) return
  openWebSocket()
}

/** Close the WebSocket connection and stop reconnection attempts. */
export function disconnectMediaWS(): void {
  if (ws) {
    ws.disconnect()
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

/** Current sequence number (for tests and debugging). */
export function getLastMediaSeq(): number {
  return lastSeq
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
    connected: ws !== null && ws.connected,
  }
}
