import { useState } from 'react'
import { Film } from 'lucide-react'
import { jobsApi } from '../../../api/client'

export interface ImageReviewCardProps {
  data: Record<string, unknown>
  jobId: string | null
}

export function ImageReviewCard({ data, jobId }: ImageReviewCardProps) {
  const scenes = (data.scenes ?? []) as Array<{
    scene_number: number
    thumbnail_url: string | null
    status: string
  }>

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [triggered, setTriggered] = useState(false)

  const handleGenerateVideos = async () => {
    if (!jobId) return
    setLoading(true)
    setError(null)
    try {
      await jobsApi.generateAllVideos(jobId)
      setTriggered(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate videos')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-lg border bg-muted p-3 text-sm">
      <div className="mb-2 font-medium">Image review</div>

      <div className="grid grid-cols-2 gap-2">
        {scenes.map((scene) => (
          <div key={scene.scene_number} className="rounded border bg-background p-2">
            <div className="mb-1 text-xs font-medium">Scene {scene.scene_number}</div>
            {scene.thumbnail_url ? (
              <img
                src={scene.thumbnail_url}
                alt={`Scene ${scene.scene_number}`}
                className="aspect-video w-full rounded object-cover"
              />
            ) : (
              <div className="flex aspect-video w-full items-center justify-center rounded bg-muted text-xs text-muted-foreground">
                No image
              </div>
            )}
            <div className="mt-1 text-xs text-muted-foreground">{scene.status}</div>
          </div>
        ))}
      </div>

      {error && <div className="mt-2 text-xs text-destructive">{error}</div>}

      <div className="mt-3">
        <button
          onClick={handleGenerateVideos}
          disabled={loading || triggered || !jobId}
          className="inline-flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          <Film className="h-3.5 w-3.5" />
          {loading ? 'Queueing...' : triggered ? 'Videos queued' : 'Generate videos'}
        </button>
      </div>
    </div>
  )
}
