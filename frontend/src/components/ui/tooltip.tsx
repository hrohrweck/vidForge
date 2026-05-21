import * as React from "react"
import { cn } from "../../lib/utils"

export interface TooltipProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'content'> {
  content: React.ReactNode
  children: React.ReactNode
}

export function Tooltip({ children, content, className, ...props }: TooltipProps) {
  return (
    <div className="group relative inline-block" {...props}>
      {children}
      <div
        className={cn(
          "pointer-events-none absolute -top-2 left-1/2 -translate-x-1/2 -translate-y-full opacity-0 transition-opacity group-hover:opacity-100",
          "z-50 overflow-hidden rounded-md border bg-popover px-3 py-1.5 text-sm text-popover-foreground shadow-md animate-in fade-in-0 zoom-in-95",
          className
        )}
      >
        {content}
      </div>
    </div>
  )
}
