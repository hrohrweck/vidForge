import { useState } from 'react'
import { Image as ImageIcon } from 'lucide-react'
import { jobsApi } from '../../../api/client'

export interface ScenePlanCardProps {
  data: Record<string, unknown>
  jobId: string | null
}

export function ScenePlanCard({ data, jobId }: ScenePlanCardProps) {
  const scenes = (data.scenes ?? []) as Array<{
    scene_number: number
    start_time: number
    end_time: number
    visual_description: string | null
    image_prompt: string | null
    mood: string
    camera_movement: string
  }>

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [triggered, setTriggered] = useState(false)

  const handleGenerateImages = async () => {
    if (!jobId) return
    setLoading(true)
    setError(null)
    try {
      await jobsApi.generateAllImages(jobId)
      setTriggered(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate images')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-lg border bg-muted p-3 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium">Scene plan</span>
        <span className="text-xs text-muted-foreground">{scenes.length} scene(s)</span>
      </div>

      <div className="max-h-60 space-y-2 overflow-y-auto pr-1">
        {scenes.map((scene) => (
          <div key={scene.scene_number} className="rounded border bg-background p-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium">Scene {scene.scene_number}</span>
              <span className="text-muted-foreground">
                {scene.start_time}s – {scene.end_time}s
              </span>
            </div>
            {scene.visual_description && (
              <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                {scene.visual_description}
              </p>
            )}
            {scene.image_prompt && (
              <p className="mt-1 line-clamp-2 text-xs italic text-muted-foreground">
                {scene.image_prompt}
              </p>
            )}
            <div className="mt-1 flex gap-2 text-xs text-muted-foreground">
              <span>Mood: {scene.mood}</span>
              <span>Camera: {scene.camera_movement}</span>
            </div>
          </div>
        ))}
      </div>

      {error && <div className="mt-2 text-xs text-destructive">{error}</div>}

      <div className="mt-3">
        <button
          onClick={handleGenerateImages}
          disabled={loading || triggered || !jobId}
          className="inline-flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          <ImageIcon className="h-3.5 w-3.5" />
          {loading ? 'Queueing...' : triggered ? 'Images queued' : 'Generate images'}
        </button>
      </div>
    </div>
  )
}
