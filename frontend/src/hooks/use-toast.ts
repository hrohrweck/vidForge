import { useCallback, useEffect, useState } from 'react'

export interface Toast {
  id: string
  message: string
  variant: 'success' | 'error'
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

export function toast(message: string, variant: 'success' | 'error' = 'success'): void {
  const id = String(++counter)
  toasts = [...toasts, { id, message, variant }]
  emit()

  const timer = setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id)
    timers.delete(id)
    emit()
  }, 4000)
  timers.set(id, timer)
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
