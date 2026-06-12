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

export interface AuthenticatedWsOptions {
  onMessage?: (event: MessageEvent) => void
  onOpen?: () => void
  onClose?: (event: CloseEvent) => void
}

/**
 * Open a WebSocket and automatically refresh the access token once on a 1008
 * (policy violation / auth failure) close.
 */
export function openAuthenticatedWebSocket(
  url: string,
  options: AuthenticatedWsOptions = {},
): WebSocket {
  const ws = new WebSocket(url)
  let retryDone = false

  ws.onopen = () => {
    retryDone = false
    options.onOpen?.()
  }

  ws.onmessage = (event) => {
    options.onMessage?.(event)
  }

  ws.onclose = async (event) => {
    options.onClose?.(event)
    if (event.code === 1008 && !retryDone) {
      retryDone = true
      const ok = await refreshAccessToken()
      if (ok) {
        openAuthenticatedWebSocket(url, options)
      }
    }
  }

  return ws
}
