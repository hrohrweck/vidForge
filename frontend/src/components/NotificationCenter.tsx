import { useCallback, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { X } from 'lucide-react'
import { useToastState, notificationToast, type Toast } from '../hooks/use-toast'
import { useNotificationFeed, connect, markRead } from '../hooks/useNotifications'
import { useAuthStore } from '../stores/auth'
import { cn } from '../lib/utils'
import type { ErrorSeverity } from '../api/types/notifications'

// Severity-based color mapping
const severityStyles: Record<ErrorSeverity, string> = {
  error: 'border-red-500/30 bg-red-500/10 text-red-200',
  critical: 'border-red-700/40 bg-red-700/20 text-red-100',
  warning: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-200',
  info: 'border-blue-500/30 bg-blue-500/10 text-blue-200',
}

/**
 * NotificationCenter renders notification toasts at the top-center of the screen.
 * 
 * - Filters toasts where variant === 'notification'
 * - Color-codes by severity (error, critical, warning, info)
 * - Stacks vertically with gap-2
 * - Click navigates to /settings/logs and marks event as read
 * - Auto-dismisses after 15s (handled by use-toast timer)
 * - Subscribes to useNotificationFeed to auto-fire on new WS events
 */
export function NotificationCenter() {
  const navigate = useNavigate()
  const { toasts, dismiss } = useToastState()
  const { events, connected } = useNotificationFeed()
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const processedEventsRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    if (isAuthenticated && !connected) {
      connect()
    }
  }, [isAuthenticated, connected])

  // Auto-fire notificationToast when new events arrive via WebSocket
  useEffect(() => {
    for (const event of events) {
      // Skip if we've already processed this event
      if (processedEventsRef.current.has(event.id)) continue
      processedEventsRef.current.add(event.id)

      // Only show toasts for error and critical severity
      if (event.severity === 'error' || event.severity === 'critical') {
        const onClick = () => {
          // Mark as read
          markRead(event.id)
          // Navigate to logs
          navigate('/settings/logs')
        }
        notificationToast(event, onClick, 1)
      }
    }

    // Clean up processed events set to prevent memory leak
    // Keep only the last 100 event IDs
    if (processedEventsRef.current.size > 100) {
      const ids = Array.from(processedEventsRef.current)
      processedEventsRef.current = new Set(ids.slice(-50))
    }
  }, [events, navigate])

  // Filter to only notification variants
  const notificationToasts = toasts.filter((t) => t.variant === 'notification')

  if (notificationToasts.length === 0) return null

  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 flex flex-col gap-2 max-w-md pointer-events-none">
      {notificationToasts.map((t) => (
        <NotificationToastItem
          key={t.id}
          toast={t}
          onDismiss={() => dismiss(t.id)}
        />
      ))}
    </div>
  )
}

interface NotificationToastItemProps {
  toast: Toast
  onDismiss: () => void
}

function NotificationToastItem({ toast, onDismiss }: NotificationToastItemProps) {
  const severity = toast.severity ?? 'error'
  const styles = severityStyles[severity]

  const handleClick = useCallback(() => {
    if (toast.onClick) {
      toast.onClick()
    }
    onDismiss()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toast.onClick, onDismiss])

  const handleDismissClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      onDismiss()
    },
    [onDismiss],
  )

  return (
    <div
      className={cn(
        'pointer-events-auto flex items-start gap-3 rounded-lg border px-4 py-3 text-sm shadow-lg backdrop-blur-sm animate-in slide-in-from-top-full fade-in duration-300',
        styles,
        toast.onClick && 'cursor-pointer'
      )}
      role="alert"
      onClick={handleClick}
    >
      <span className="flex-1">{toast.message}</span>
      <button
        onClick={handleDismissClick}
        className="shrink-0 opacity-70 hover:opacity-100 transition-opacity"
        aria-label="Dismiss"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}
