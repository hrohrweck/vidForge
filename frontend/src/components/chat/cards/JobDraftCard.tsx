import { useState } from 'react'
import { jobsApi } from '../../../api/client'

export interface JobDraftCardProps {
  data: Record<string, unknown>
  jobId: string | null
}

export function JobDraftCard({ data, jobId }: JobDraftCardProps) {
  const draft = data as {
    template: string
    prompt: string
    duration: number
    style: string
    aspect_ratio: string
    avatars?: Array<{ avatar_id: string; avatar_name?: string }>
    image_model?: string
    video_model?: string
  }

  const [prompt, setPrompt] = useState(draft.prompt ?? '')
  const [duration, setDuration] = useState<number | ''>(draft.duration ?? 30)
  const [style, setStyle] = useState(draft.style ?? 'realistic')
  const [aspectRatio, setAspectRatio] = useState(draft.aspect_ratio ?? '16:9')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState(false)

  const disabled = loading || created

  const handleCreate = async () => {
    setLoading(true)
    setError(null)
    try {
      await jobsApi.create({
        title: prompt.slice(0, 50),
        template_id: draft.template,
        input_data: {
          prompt,
          duration: typeof duration === 'number' ? duration : Number(duration),
          style,
          aspect_ratio: aspectRatio,
          avatars: draft.avatars,
          image_model: draft.image_model,
          video_model: draft.video_model,
        },
        auto_start: true,
      })
      setCreated(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create job')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-lg border bg-muted p-3 text-sm">
      <div className="mb-2 font-medium">{jobId ? `Job draft (${jobId})` : 'Job draft'}</div>

      <div className="space-y-2">
        <div>
          <label className="block text-xs text-muted-foreground">Prompt</label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={disabled}
            className="w-full rounded border bg-background px-2 py-1 text-sm disabled:opacity-60"
            rows={3}
          />
        </div>

        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="block text-xs text-muted-foreground">Duration</label>
            <input
              type="number"
              value={duration}
              onChange={(e) => setDuration(e.target.value === '' ? '' : Number(e.target.value))}
              disabled={disabled}
              className="w-full rounded border bg-background px-2 py-1 text-sm disabled:opacity-60"
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Style</label>
            <input
              type="text"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
              disabled={disabled}
              className="w-full rounded border bg-background px-2 py-1 text-sm disabled:opacity-60"
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Aspect</label>
            <input
              type="text"
              value={aspectRatio}
              onChange={(e) => setAspectRatio(e.target.value)}
              disabled={disabled}
              className="w-full rounded border bg-background px-2 py-1 text-sm disabled:opacity-60"
            />
          </div>
        </div>

        {draft.avatars && draft.avatars.length > 0 && (
          <div>
            <label className="block text-xs text-muted-foreground">Avatars</label>
            <div className="text-xs text-muted-foreground">
              {draft.avatars.map((a) => a.avatar_name ?? a.avatar_id).join(', ')}
            </div>
          </div>
        )}

        {(draft.image_model || draft.video_model) && (
          <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
            {draft.image_model && <div>Image model: {draft.image_model}</div>}
            {draft.video_model && <div>Video model: {draft.video_model}</div>}
          </div>
        )}
      </div>

      {created && (
        <div className="mt-2 text-xs text-green-600">Job created and started.</div>
      )}

      {error && (
        <div className="mt-2 text-xs text-destructive">{error}</div>
      )}

      <div className="mt-3 flex gap-2">
        <button
          onClick={handleCreate}
          disabled={disabled}
          className="rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {loading ? 'Creating...' : 'Create'}
        </button>
      </div>
    </div>
  )
}
