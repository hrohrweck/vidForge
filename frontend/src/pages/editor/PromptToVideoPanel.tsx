/**
 * Prompt-to-Video sidebar panel + planning form.
 *
 * Handles prompt enhancement and scene planning for the prompt-to-video
 * template. Users enter a text prompt, set style/duration, then the LLM
 * breaks it into visual segments.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { scenesApi, type Job, type VideoScene } from '../../api/client'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'

interface Props {
  job: Job | undefined
  jobId: string
  scenes: VideoScene[] | undefined
  planningMode?: boolean
}

export function PromptToVideoPanel({ job, jobId, scenes, planningMode }: Props) {
  const queryClient = useQueryClient()

  const [prompt, setPrompt] = useState(
    (job?.input_data?.prompt as string) || '',
  )
  const [duration, setDuration] = useState(
    (job?.input_data?.duration as number) || 10,
  )
  const [style, setStyle] = useState(
    (job?.input_data?.style as string) || 'realistic',
  )

  const planScenesMutation = useMutation({
    mutationFn: async () => {
      // For prompt-to-video, we POST to the generic plan endpoint
      // with the prompt as lyrics_data (the planner interprets it)
      return scenesApi.planScenes(jobId, {
        lyrics_data: { full_text: prompt },
        duration,
        style,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scenes', jobId] })
      queryClient.invalidateQueries({ queryKey: ['job', jobId] })
    },
  })

  // ── Planning mode ─────────────────────────────────────────────────

  if (planningMode) {
    return (
      <div className="lg:col-span-3">
        <div className="bg-card rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-4">Create Your Video from a Prompt</h2>
          <p className="text-sm text-muted-foreground mb-4">
            Enter a description of the video you want. The AI will break it into
            3–6 second visual scenes.
          </p>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Prompt</Label>
              <textarea
                className="w-full h-32 rounded-md border border-input bg-background px-3 py-2"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="A serene mountain landscape at sunrise, birds flying across a golden sky..."
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Duration (seconds)</Label>
                <Input
                  type="number"
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                  min={3}
                  max={60}
                />
              </div>
              <div className="space-y-2">
                <Label>Style</Label>
                <select
                  className="w-full h-10 rounded-md border border-input bg-background px-3 py-2"
                  value={style}
                  onChange={(e) => setStyle(e.target.value)}
                >
                  <option value="realistic">Realistic</option>
                  <option value="anime">Anime</option>
                  <option value="manga">Manga</option>
                  <option value="cinematic">Cinematic</option>
                  <option value="abstract">Abstract</option>
                </select>
              </div>
            </div>

            <Button
              onClick={() => planScenesMutation.mutate()}
              disabled={planScenesMutation.isPending || !prompt.trim()}
            >
              {planScenesMutation.isPending ? 'Planning Scenes...' : 'Generate Scene Plan'}
            </Button>

            {job?.stage === 'planning' && scenes && scenes.length > 0 && (
              <div className="mt-4 p-4 bg-primary/10 rounded-lg border border-primary/20">
                <p className="text-sm text-primary mb-2">
                  {scenes.length} scenes planned. You can continue to the editor or regenerate.
                </p>
                <Button
                  onClick={() =>
                    scenesApi.updateStage(jobId, 'planned').then(() =>
                      queryClient.invalidateQueries({ queryKey: ['job', jobId] }),
                    )
                  }
                >
                  Continue to Scene Editor
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ── Sidebar mode ──────────────────────────────────────────────────

  return (
    <div className="bg-card rounded-lg border p-4">
      <h3 className="font-semibold mb-2">Prompt</h3>
      <p className="text-sm text-muted-foreground">
        {(job?.input_data?.prompt as string) || '—'}
      </p>
      <div className="mt-3 space-y-1 text-sm text-muted-foreground">
        <div className="flex justify-between">
          <span>Duration:</span>
          <span>{duration}s</span>
        </div>
        <div className="flex justify-between">
          <span>Style:</span>
          <span className="capitalize">{style}</span>
        </div>
      </div>
    </div>
  )
}
