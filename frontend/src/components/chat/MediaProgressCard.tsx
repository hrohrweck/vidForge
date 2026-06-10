import { useEffect, useState } from 'react'
import { Progress } from '../ui/progress'
import { Loader2, CheckCircle, XCircle } from 'lucide-react'

interface MediaProgressCardProps {
  taskId: string
  onComplete?: (url: string) => void
}

export function MediaProgressCard({ taskId }: MediaProgressCardProps) {
  const [status] = useState<'generating' | 'completed' | 'failed'>('generating')
  const [resultUrl] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const interval = setInterval(async () => {
      // Poll for status — simplified: just show indefinite progress
      // In production, poll the actual API endpoint
      setProgress((p) => Math.min(p + 5, 95))
    }, 2000)
    return () => clearInterval(interval)
  }, [taskId])

  return (
    <div className="mt-2 rounded-lg border bg-muted/30 p-3">
      {status === 'generating' && (
        <div className="flex items-center gap-3">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          <div className="flex-1">
            <div className="mb-1 text-xs text-muted-foreground">Generating media...</div>
            <Progress value={progress} className="h-1.5" />
          </div>
        </div>
      )}
      {status === 'completed' && resultUrl && (
        <div className="flex items-center gap-2">
          <CheckCircle className="h-4 w-4 text-green-500" />
          <span className="text-xs">Media ready</span>
          <img
            src={resultUrl}
            alt="Generated"
            className="ml-auto max-h-[150px] max-w-[200px] rounded"
          />
        </div>
      )}
      {status === 'failed' && (
        <div className="flex items-center gap-2 text-destructive">
          <XCircle className="h-4 w-4" />
          <span className="text-xs">Generation failed</span>
        </div>
      )}
    </div>
  )
}
