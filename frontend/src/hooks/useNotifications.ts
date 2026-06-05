/**
 * Module-level singleton WebSocket client for real-time notifications.
 *
 * Pattern mirrors `use-toast.ts`: module-level state + listener Set + emit.
 * Exposes both imperative functions (connect, disconnect, markRead, etc.)
 * and a React hook (useNotificationFeed) for components.
 */

import { useCallback, useEffect, useState } from 'react'
import api from '../api/client'
import type { ErrorEvent, ErrorEventListResponse } from '../api/types/notifications'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NotificationState {
  events: ErrorEvent[]
  unreadCount: number
  connected: boolean
}

type Listener = (state: NotificationState) => void

/** Raw WS payload shape (snake_case from Python dispatcher). */
interface WsPayload {
  type: string
  id: string
  user_id: string | null
  severity: string
  origin: string
  message: string
  source_id: string | null
  source_type: string | null
  created_at: string | null
  read_at: string | null
}

// ---------------------------------------------------------------------------
// Module-level singleton state
// ---------------------------------------------------------------------------

const listeners = new Set<Listener>()

let state: NotificationState = {
  events: [],
  unreadCount: 0,
  connected: false,
}

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectAttempt = 0
let currentToken: string | null = null
let intentionalClose = false

const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function emit(): void {
  const snapshot = { ...state, events: [...state.events] }
  listeners.forEach((l) => l(snapshot))
}

function setState(partial: Partial<NotificationState>): void {
  state = { ...state, ...partial }
  emit()
}

/** Convert a snake_case WS payload into the camelCase ErrorEvent shape. */
function wsPayloadToErrorEvent(payload: WsPayload): ErrorEvent {
  return {
    id: payload.id,
    userId: payload.user_id,
    severity: payload.severity as ErrorEvent['severity'],
    origin: payload.origin as ErrorEvent['origin'],
    message: payload.message,
    sourceId: payload.source_id,
    sourceType: payload.source_type,
    createdAt: payload.created_at ?? '',
    readAt: payload.read_at,
  }
}

/** Derive WebSocket base URL from the current page location. */
function getWsBaseUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

function scheduleReconnect(): void {
  if (intentionalClose || !currentToken) return

  const delay = Math.min(
    RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt),
    RECONNECT_MAX_MS,
  )
  reconnectAttempt++

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    openWebSocket(currentToken!)
  }, delay)
}

function openWebSocket(token: string): void {
  // Clean up any existing connection
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
  ws = new WebSocket(`${baseUrl}/ws/notifications?token=${encodeURIComponent(token)}`)

  ws.onopen = () => {
    reconnectAttempt = 0
    setState({ connected: true })
    // Fetch current unread count on connect
    fetchUnreadCount()
  }

  ws.onmessage = (event: MessageEvent) => {
    try {
      const payload = JSON.parse(event.data as string) as WsPayload
      if (payload.type === 'error_event') {
        const errorEvent = wsPayloadToErrorEvent(payload)
        setState({
          events: [errorEvent, ...state.events],
          unreadCount: state.unreadCount + 1,
        })
      }
    } catch {
      // Ignore malformed messages
    }
  }

  ws.onclose = () => {
    ws = null
    setState({ connected: false })
    scheduleReconnect()
  }

  ws.onerror = () => {
    // onclose will fire after onerror, so reconnect is handled there
  }
}

async function fetchUnreadCount(): Promise<void> {
  try {
    const response = await api.get<{ unreadCount: number }>('/notifications/unread-count')
    setState({ unreadCount: response.data.unreadCount })
  } catch {
    // Silently fail — will retry on next connect
  }
}

// ---------------------------------------------------------------------------
// Public imperative API
// ---------------------------------------------------------------------------

/** Open a WebSocket connection for real-time notifications. */
export function connect(token: string): void {
  intentionalClose = false
  currentToken = token
  reconnectAttempt = 0

  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  openWebSocket(token)
}

/** Close the WebSocket connection and stop reconnection attempts. */
export function disconnect(): void {
  intentionalClose = true
  currentToken = null

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

  setState({ connected: false })
}

/** Mark a single notification as read via REST API. */
export async function markRead(eventId: string): Promise<void> {
  try {
    await api.post(`/notifications/${eventId}/read`)
    // Update local state: mark event as read and decrement unread count
    setState({
      events: state.events.map((e) =>
        e.id === eventId ? { ...e, readAt: new Date().toISOString() } : e,
      ),
      unreadCount: Math.max(0, state.unreadCount - 1),
    })
  } catch {
    // Let the caller handle errors if needed
  }
}

/** Mark all notifications as read via REST API. */
export async function markAllRead(): Promise<void> {
  try {
    await api.post('/notifications/mark-all-read')
    setState({
      events: state.events.map((e) =>
        e.readAt ? e : { ...e, readAt: new Date().toISOString() },
      ),
      unreadCount: 0,
    })
  } catch {
    // Let the caller handle errors if needed
  }
}

/** Refresh the event list from the REST API. */
export async function refresh(): Promise<void> {
  try {
    const response = await api.get<ErrorEventListResponse>('/notifications')
    setState({
      events: response.data.items,
      unreadCount: response.data.unreadCount,
    })
  } catch {
    // Silently fail — state remains unchanged
  }
}

// ---------------------------------------------------------------------------
// React hook
// ---------------------------------------------------------------------------

/**
 * React hook that subscribes to the notification singleton state.
 *
 * Returns the current events, unread count, connection status,
 * and stable references to the imperative functions.
 */
export function useNotificationFeed() {
  const [feedState, setFeedState] = useState<NotificationState>(state)

  useEffect(() => {
    const listener: Listener = (next) => setFeedState(next)
    listeners.add(listener)
    // Sync in case state changed between render and effect
    setFeedState(state)
    return () => {
      listeners.delete(listener)
    }
  }, [])

  const stableMarkRead = useCallback((eventId: string) => markRead(eventId), [])
  const stableMarkAllRead = useCallback(() => markAllRead(), [])
  const stableRefresh = useCallback(() => refresh(), [])

  return {
    events: feedState.events,
    unreadCount: feedState.unreadCount,
    connected: feedState.connected,
    markRead: stableMarkRead,
    markAllRead: stableMarkAllRead,
    refresh: stableRefresh,
  }
}
