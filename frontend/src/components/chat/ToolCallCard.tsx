interface ToolCallCardProps {
  name: string
  status: 'running' | 'success' | 'error'
  argsPreview?: object
  result?: object | string | number | boolean | null
  error?: string
}

const STATUS_STYLES = {
  running: 'bg-yellow-500/20 text-yellow-700 dark:bg-yellow-500/30 dark:text-yellow-300',
  success: 'bg-green-500/20 text-green-700 dark:bg-green-500/30 dark:text-green-300',
  error: 'bg-red-500/20 text-red-700 dark:bg-red-500/30 dark:text-red-300',
}

export function ToolCallCard({ name, status, argsPreview, result, error }: ToolCallCardProps) {
  return (
    <div className="mb-3 rounded-lg bg-muted px-4 py-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-foreground">{name}</span>
        <span className={`rounded px-2 py-0.5 text-xs ${STATUS_STYLES[status]}`}>
          {status}
        </span>
      </div>

      {argsPreview && (
        <div className="mt-2">
          <p className="text-xs text-muted-foreground">Arguments:</p>
          <pre className="mt-1 overflow-x-auto rounded bg-black/10 p-2 text-xs dark:bg-white/10">
            {JSON.stringify(argsPreview, null, 2)}
          </pre>
        </div>
      )}

      {error && (
        <div className="mt-2">
          <p className="text-xs text-red-600 dark:text-red-400">Error:</p>
          <pre className="mt-1 overflow-x-auto rounded bg-red-500/10 p-2 text-xs text-red-600 dark:text-red-400">
            {error}
          </pre>
        </div>
      )}

      {result && (
        <div className="mt-2">
          <p className="text-xs text-muted-foreground">Result:</p>
          <pre className="mt-1 overflow-x-auto rounded bg-black/10 p-2 text-xs dark:bg-white/10">
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}