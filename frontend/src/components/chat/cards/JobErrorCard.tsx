import { useState } from 'react'
import { jobsApi } from '../../../api/client'

export interface JobErrorCardProps {
  data: Record<string, unknown>
  jobId: string | null
}

export function JobErrorCard({ data, jobId }: JobErrorCardProps) {
  const result = data as { error_message: string }
  const [loading, setLoading] = useState<'retry' | 'cancel' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [actioned, setActioned] = useState<'retried' | 'cancelled' | null>(null)

  const handleRetry = async () => {
    if (!jobId) return
    setLoading('retry')
    setError(null)
    try {
      await jobsApi.retry(jobId)
      setActioned('retried')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry')
    } finally {
      setLoading(null)
    }
  }

  const handleCancel = async () => {
    if (!jobId) return
    setLoading('cancel')
    setError(null)
    try {
      await jobsApi.cancel(jobId)
      setActioned('cancelled')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel')
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
      <div className="mb-2 font-medium text-destructive">Job error</div>
      {jobId && <div className="mb-2 text-xs text-muted-foreground">Job ID: {jobId}</div>}

      <div className="mb-2 text-sm text-destructive">{result.error_message}</div>

      {actioned && (
        <div className="mb-2 text-xs text-green-600">
          {actioned === 'retried' ? 'Retry queued.' : 'Job cancelled.'}
        </div>
      )}

      {error && <div className="mb-2 text-xs text-destructive">{error}</div>}

      <div className="flex gap-2">
        <button
          onClick={handleRetry}
          disabled={loading !== null || !!actioned || !jobId}
          className="rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {loading === 'retry' ? 'Retrying...' : 'Retry'}
        </button>
        <button
          onClick={handleCancel}
          disabled={loading !== null || !!actioned || !jobId}
          className="rounded bg-muted px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted/80 disabled:opacity-50"
        >
          {loading === 'cancel' ? 'Cancelling...' : 'Cancel'}
        </button>
      </div>
    </div>
  )
}
