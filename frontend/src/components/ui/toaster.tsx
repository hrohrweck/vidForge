import { useToastState } from '../../hooks/use-toast'
import { cn } from '../../lib/utils'
import { X } from 'lucide-react'

const variantStyles: Record<string, string> = {
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  error: 'border-red-500/30 bg-red-500/10 text-red-200',
  notification: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
}

export function Toaster() {
  const { toasts, dismiss } = useToastState()

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            'pointer-events-auto flex items-start gap-3 rounded-lg border px-4 py-3 text-sm shadow-lg backdrop-blur-sm animate-in slide-in-from-right-full fade-in',
            variantStyles[t.variant]
          )}
          role="alert"
          onClick={t.onClick}
          style={t.onClick ? { cursor: 'pointer' } : undefined}
        >
          <span className="flex-1">{t.message}</span>
          <button
            onClick={(e) => {
              e.stopPropagation()
              dismiss(t.id)
            }}
            className="shrink-0 opacity-70 hover:opacity-100 transition-opacity"
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  )
}
