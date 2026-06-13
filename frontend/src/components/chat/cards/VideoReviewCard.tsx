import { useState } from 'react'
import { Download } from 'lucide-react'
import { jobsApi } from '../../../api/client'

export interface VideoReviewCardProps {
  data: Record<string, unknown>
  jobId: string | null
}

export function VideoReviewCard({ data, jobId }: VideoReviewCardProps) {
  const scenes = (data.scenes ?? []) as Array<{
    scene_number: number
    preview_url: string | null
    status: string
  }>

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [triggered, setTriggered] = useState(false)

  const handleExport = async () => {
    if (!jobId) return
    setLoading(true)
    setError(null)
    try {
      await jobsApi.export(jobId, {})
      setTriggered(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-lg border bg-muted p-3 text-sm">
      <div className="mb-2 font-medium">Video review</div>

      <div className="grid grid-cols-2 gap-2">
        {scenes.map((scene) => (
          <div key={scene.scene_number} className="rounded border bg-background p-2">
            <div className="mb-1 text-xs font-medium">Scene {scene.scene_number}</div>
            {scene.preview_url ? (
              <video
                src={scene.preview_url}
                controls
                className="aspect-video w-full rounded"
              />
            ) : (
              <div className="flex aspect-video w-full items-center justify-center rounded bg-muted text-xs text-muted-foreground">
                No video
              </div>
            )}
            <div className="mt-1 text-xs text-muted-foreground">{scene.status}</div>
          </div>
        ))}
      </div>

      {error && <div className="mt-2 text-xs text-destructive">{error}</div>}

      <div className="mt-3">
        <button
          onClick={handleExport}
          disabled={loading || triggered || !jobId}
          className="inline-flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          <Download className="h-3.5 w-3.5" />
          {loading ? 'Exporting...' : triggered ? 'Export queued' : 'Export'}
        </button>
      </div>
    </div>
  )
}
