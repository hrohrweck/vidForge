import { useAuthStore } from '../stores/auth'

/**
 * Refresh the short-lived access-token cookie.
 *
 * WebSocket handshakes cannot carry custom headers, so the backend reads the
 * access token from cookies. If that cookie has expired, the WebSocket is
 * rejected with close code 1008. Calling /auth/refresh re-issues the cookie.
 *
 * Returns true when a fresh cookie was obtained, false otherwise. A 401 from
 * refresh means the session is gone, so we log the user out.
 */
export async function refreshAccessToken(): Promise<boolean> {
  try {
    const response = await fetch('/api/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    })
    if (response.status === 401) {
      useAuthStore.getState().logout()
      return false
    }
    return response.ok
  } catch {
    return false
  }
}

// ---------------------------------------------------------------------------
// Persistent WebSocket client
// ---------------------------------------------------------------------------

const DEFAULT_HEARTBEAT_TIMEOUT_MS = 60_000
const DEFAULT_RECONNECT_BASE_MS = 1_000
const DEFAULT_RECONNECT_MAX_MS = 30_000

export interface PersistentWebSocketOptions {
  url: string
  heartbeatIntervalMs?: number
  heartbeatTimeoutMs?: number
  reconnect?: boolean
  reconnectBaseMs?: number
  reconnectMaxMs?: number
  onMessage?: (event: MessageEvent) => void
  onOpen?: () => void
  onClose?: (event: CloseEvent) => void
  authRetry?: boolean
}

/**
 * Manages a single WebSocket connection with automatic heartbeat, auth-token
 * refresh, and exponential-backoff reconnect.
 *
 * The backend sends `{"type":"ping"}` periodically. This client replies with
 * `{"type":"pong"}` and forcibly reconnects if no frame is received within the
 * configured heartbeat timeout.
 */
export class PersistentWebSocket {
  private ws: WebSocket | null = null
  private heartbeatTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectAttempt = 0
  private intentionalClose = false
  private authRetryDone = false
  private lastUrl: string

  constructor(private options: PersistentWebSocketOptions) {
    this.lastUrl = options.url
  }

  /** Open (or reopen) the WebSocket. */
  connect(url?: string): void {
    if (url) {
      this.lastUrl = url
    }
    this.intentionalClose = false
    this._clearReconnect()
    this._open()
  }

  /** Close the WebSocket and stop reconnection attempts. */
  disconnect(): void {
    this.intentionalClose = true
    this._clearReconnect()
    this._clearHeartbeat()
    this._closeSocket()
  }

  /** Send raw data if the socket is open. */
  send(data: string): boolean {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(data)
      return true
    }
    return false
  }

  /** True when the underlying WebSocket is OPEN. */
  get connected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN
  }

  private _open(): void {
    this._closeSocket()

    const ws = new WebSocket(this.lastUrl)
    this.ws = ws

    ws.onopen = () => {
      this.reconnectAttempt = 0
      this.authRetryDone = false
      this._resetHeartbeat()
      this.options.onOpen?.()
    }

    ws.onmessage = (event: MessageEvent) => {
      this._resetHeartbeat()

      // Fast path for backend pings so they do not leak into onMessage handlers.
      if (typeof event.data === 'string') {
        const trimmed = event.data.trim()
        if (trimmed === '{"type":"ping"}' || trimmed === '{"type": "ping"}') {
          this.send('{"type":"pong"}')
          return
        }
      }

      this.options.onMessage?.(event)
    }

    ws.onclose = (event: CloseEvent) => {
      this.ws = null
      this._clearHeartbeat()
      this.options.onClose?.(event)
      if (!this.intentionalClose) {
        this._scheduleReconnect(event.code)
      }
    }

    ws.onerror = () => {
      // onclose always follows onerror; reconnect is handled there.
    }
  }

  private _closeSocket(): void {
    const ws = this.ws
    if (!ws) return

    ws.onopen = null
    ws.onmessage = null
    ws.onclose = null
    ws.onerror = null

    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close()
    }
    this.ws = null
  }

  private _resetHeartbeat(): void {
    this._clearHeartbeat()
    const timeout = this.options.heartbeatTimeoutMs ?? DEFAULT_HEARTBEAT_TIMEOUT_MS
    this.heartbeatTimer = setTimeout(() => {
      this.heartbeatTimer = null
      // Force close so onclose fires and triggers reconnect logic.
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.close()
      }
    }, timeout)
  }

  private _clearHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearTimeout(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  private _scheduleReconnect(closeCode: number): void {
    if (this.reconnectTimer) return

    const reconnect = this.options.reconnect ?? true
    if (!reconnect) return

    if (closeCode === 1008 && this.options.authRetry !== false && !this.authRetryDone) {
      this.authRetryDone = true
      refreshAccessToken().then((ok) => {
        if (ok) {
          this.reconnectAttempt = 0
          this._open()
        } else {
          this._backoffReconnect()
        }
      })
      return
    }

    this._backoffReconnect()
  }

  private _backoffReconnect(): void {
    const base = this.options.reconnectBaseMs ?? DEFAULT_RECONNECT_BASE_MS
    const max = this.options.reconnectMaxMs ?? DEFAULT_RECONNECT_MAX_MS
    const delay = Math.min(base * Math.pow(2, this.reconnectAttempt), max)
    this.reconnectAttempt++

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this._open()
    }, delay)
  }

  private _clearReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }
}

// ---------------------------------------------------------------------------
// React hook wrapper
// ---------------------------------------------------------------------------

import { useCallback, useEffect, useRef, useState } from 'react'

export interface UsePersistentWebSocketOptions {
  url: string
  heartbeatIntervalMs?: number
  heartbeatTimeoutMs?: number
  reconnect?: boolean
  reconnectBaseMs?: number
  reconnectMaxMs?: number
  onMessage?: (event: MessageEvent) => void
  onOpen?: () => void
  onClose?: (event: CloseEvent) => void
  authRetry?: boolean
  connect?: boolean
}

export interface UsePersistentWebSocketResult {
  connected: boolean
  send: (data: string) => boolean
  reconnect: () => void
  disconnect: () => void
}

/**
 * React hook that manages a PersistentWebSocket for the lifetime of a
 * component. Reconnects automatically when the URL changes.
 */
export function usePersistentWebSocket(
  options: UsePersistentWebSocketOptions,
): UsePersistentWebSocketResult {
  const optionsRef = useRef(options)
  optionsRef.current = options

  const [connected, setConnected] = useState(false)
  const wsRef = useRef<PersistentWebSocket | null>(null)

  useEffect(() => {
    const ws = new PersistentWebSocket({
      url: options.url,
      heartbeatIntervalMs: options.heartbeatIntervalMs,
      heartbeatTimeoutMs: options.heartbeatTimeoutMs,
      reconnect: options.reconnect,
      reconnectBaseMs: options.reconnectBaseMs,
      reconnectMaxMs: options.reconnectMaxMs,
      authRetry: options.authRetry,
      onOpen: () => {
        setConnected(true)
        optionsRef.current.onOpen?.()
      },
      onClose: (event) => {
        setConnected(false)
        optionsRef.current.onClose?.(event)
      },
      onMessage: (event) => optionsRef.current.onMessage?.(event),
    })

    wsRef.current = ws
    if (options.connect !== false) {
      ws.connect()
    }

    return () => {
      ws.disconnect()
    }
  }, [options.url])

  const send = useCallback((data: string) => wsRef.current?.send(data) ?? false, [])
  const reconnect = useCallback(() => wsRef.current?.connect(), [])
  const disconnect = useCallback(() => wsRef.current?.disconnect(), [])

  return { connected, send, reconnect, disconnect }
}

