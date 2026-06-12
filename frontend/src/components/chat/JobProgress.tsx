import { useEffect, useRef, useState } from 'react'
import { refreshAccessToken } from '../../lib/websocket'

interface JobProgressProps {
  jobId: string
  onComplete?: (payload: { output_path?: string; preview_path?: string; status: string }) => void
}

interface WSMessage {
  type: 'progress' | 'completed' | 'error' | 'failed' | 'status_update'
  job_id: string
  progress?: number
  status?: string
  output_path?: string
  preview_path?: string
}

export default function JobProgress({ jobId, onComplete }: JobProgressProps) {
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState<string>('queued')
  const [done, setDone] = useState(false)

  const authRetryDone = useRef(false)

  useEffect(() => {
    if (done) return

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/jobs/${jobId}`
    const ws = new WebSocket(wsUrl)

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data)
        if (msg.job_id !== jobId) return
        if (typeof msg.progress === 'number') setProgress(msg.progress)
        if (msg.status) setStatus(msg.status)
        const isTerminal =
          msg.type === 'completed' ||
          msg.type === 'failed' ||
          (msg.type === 'status_update' &&
            (msg.status === 'completed' || msg.status === 'failed'))
        if (isTerminal) {
          setDone(true)
          onComplete?.({
            output_path: msg.output_path,
            preview_path: msg.preview_path,
            status: msg.status ?? msg.type,
          })
          ws.close()
        }
      } catch (e) {
        console.error('job ws parse', e)
      }
    }

    ws.onclose = async (event) => {
      // 1008 = policy violation; the access-token cookie expired. Refresh it
      // once and let the effect reopen the socket on the next render cycle.
      if (event.code === 1008 && !authRetryDone.current) {
        authRetryDone.current = true
        await refreshAccessToken()
      }
    }

    return () => ws.close()
  }, [jobId, done, onComplete])

  return (
    <div
      role="progressbar"
      aria-valuenow={progress}
      aria-valuemin={0}
      aria-valuemax={100}
      className="mt-2 w-full"
    >
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="capitalize">{status.replace(/_/g, ' ')}</span>
        <span>{progress}%</span>
      </div>
      <div className="h-1.5 w-full rounded bg-muted overflow-hidden">
        <div
          className={`h-full transition-all ${status === 'failed' ? 'bg-destructive' : 'bg-primary'}`}
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  )
}
