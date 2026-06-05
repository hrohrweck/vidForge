import { useCallback, useEffect, useState } from 'react'

import type { ErrorSeverity } from '../api/types/notifications'

export interface Toast {
  id: string
  message: string
  variant: 'success' | 'error' | 'notification'
  eventId?: string
  severity?: ErrorSeverity
  count?: number
  onClick?: () => void
  duration?: number
}

type Listener = (toasts: Toast[]) => void
const listeners = new Set<Listener>()
let toasts: Toast[] = []
let counter = 0

function emit(): void {
  const snapshot = [...toasts]
  listeners.forEach((l) => l(snapshot))
}

const timers = new Map<string, ReturnType<typeof setTimeout>>()

/** Show a simple toast (backward-compatible) or pass a full Toast options object. */
export function toast(message: string, variant?: 'success' | 'error'): void
export function toast(options: Omit<Toast, 'id'> & { id?: string }): void
export function toast(
  messageOrOptions: string | (Omit<Toast, 'id'> & { id?: string }),
  variant: 'success' | 'error' = 'success',
): void {
  let entry: Toast

  if (typeof messageOrOptions === 'string') {
    entry = { id: String(++counter), message: messageOrOptions, variant }
  } else {
    entry = { ...messageOrOptions, id: messageOrOptions.id ?? String(++counter) }
  }

  const duration = entry.duration ?? 4000

  toasts = [...toasts, entry]
  emit()

  const timer = setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== entry.id)
    timers.delete(entry.id)
    emit()
  }, duration)
  timers.set(entry.id, timer)
}

/**
 * Show a notification toast with deduplication by eventId.
 *
 * If a toast with the same eventId already exists, its count and message are
 * updated in-place and the auto-dismiss timer is reset (no duplicate entry).
 *
 * @param event  - Minimal event shape (id used for dedup, message displayed, severity optional)
 * @param onClick - Optional click handler attached to the toast
 * @param count  - Total number of merged events (appends "(+N more)" when > 1)
 */
export function notificationToast(
  event: { id: string; message: string; severity?: ErrorSeverity },
  onClick?: () => void,
  count: number = 1,
): void {
  const message =
    count > 1 ? `${event.message} (+${count - 1} more)` : event.message

  // Dedup: check if a toast with this eventId already exists
  const existing = toasts.find((t) => t.eventId === event.id)

  if (existing) {
    const existingId = existing.id

    // Clear the current auto-dismiss timer
    const existingTimer = timers.get(existingId)
    if (existingTimer) {
      clearTimeout(existingTimer)
      timers.delete(existingId)
    }

    // Update the toast in place (new message, count, onClick, severity)
    toasts = toasts.map((t) =>
      t.id === existingId
        ? { ...t, message, count, onClick, severity: event.severity }
        : t,
    )
    emit()

    // Reset the auto-dismiss timer
    const duration = existing.duration ?? 15000
    const timer = setTimeout(() => {
      toasts = toasts.filter((t) => t.id !== existingId)
      timers.delete(existingId)
      emit()
    }, duration)
    timers.set(existingId, timer)
  } else {
    // No existing toast — create a new one
    toast({
      message,
      variant: 'notification',
      eventId: event.id,
      severity: event.severity,
      count,
      onClick,
      duration: 15000,
    })
  }
}

export function dismissToast(id: string): void {
  const timer = timers.get(id)
  if (timer) {
    clearTimeout(timer)
    timers.delete(id)
  }
  toasts = toasts.filter((t) => t.id !== id)
  emit()
}

export function useToastState() {
  const [state, setState] = useState<Toast[]>(toasts)

  useEffect(() => {
    const listener: Listener = (next) => setState(next)
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }, [])

  const dismiss = useCallback((id: string) => dismissToast(id), [])

  return { toasts: state, dismiss }
}
