/**
 * Script-to-Video sidebar panel + planning form.
 *
 * Handles script editing with bracket annotation support and TTS voice
 * selection for the script-to-video template.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { scenesApi, type Job, type VideoScene } from '../../api/client'
import { Button } from '../../components/ui/button'
import { Label } from '../../components/ui/label'

interface Props {
  job: Job | undefined
  jobId: string
  scenes: VideoScene[] | undefined
  planningMode?: boolean
}

export function ScriptToVideoPanel({ job, jobId, scenes, planningMode }: Props) {
  const queryClient = useQueryClient()

  const [script, setScript] = useState(
    (job?.input_data?.script as string) || '',
  )
  const [style, setStyle] = useState(
    (job?.input_data?.style as string) || 'realistic',
  )
  const [voice, setVoice] = useState(
    (job?.input_data?.voice as string) || 'default',
  )

  const planScenesMutation = useMutation({
    mutationFn: async () => {
      return scenesApi.planScenes(jobId, {
        lyrics_data: { full_text: script },
        duration: 30,
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
          <h2 className="text-lg font-semibold mb-4">Create Your Video from a Script</h2>
          <p className="text-sm text-muted-foreground mb-4">
            Write your script with visual directions in [square brackets].
            The AI will plan scenes and generate narration.
          </p>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Script</Label>
              <textarea
                className="w-full h-48 rounded-md border border-input bg-background px-3 py-2 font-mono text-sm"
                value={script}
                onChange={(e) => setScript(e.target.value)}
                placeholder={`Welcome to our channel. [Show a beautiful sunset over mountains]\n\nToday we'll explore the wonders of nature. [Cut to a flowing river]\n\nLet's begin our journey. [Aerial shot of a forest]`}
              />
              <p className="text-xs text-muted-foreground">
                Use [brackets] for visual directions. Text outside brackets will be narrated.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Visual Style</Label>
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
              <div className="space-y-2">
                <Label>Narration Voice</Label>
                <select
                  className="w-full h-10 rounded-md border border-input bg-background px-3 py-2"
                  value={voice}
                  onChange={(e) => setVoice(e.target.value)}
                >
                  <option value="default">Default (Andrew)</option>
                  <option value="male">Male (Guy)</option>
                  <option value="female">Female (Jenny)</option>
                  <option value="deep">Deep (Davis)</option>
                  <option value="none">No Narration</option>
                </select>
              </div>
            </div>

            <Button
              onClick={() => planScenesMutation.mutate()}
              disabled={planScenesMutation.isPending || !script.trim()}
            >
              {planScenesMutation.isPending ? 'Planning Scenes...' : 'Generate Scene Plan'}
            </Button>

            {job?.stage === 'planning' && scenes && scenes.length > 0 && (
              <div className="mt-4 p-4 bg-primary/10 rounded-lg border border-primary/20">
                <p className="text-sm text-primary mb-2">
                  {scenes.length} scenes planned. Continue to the editor or regenerate.
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

  const segmentCount = (script.match(/\[[^\]]+\]/g) || []).length

  return (
    <div className="bg-card rounded-lg border p-4">
      <h3 className="font-semibold mb-2">Script</h3>
      <div className="text-sm text-muted-foreground max-h-48 overflow-y-auto whitespace-pre-wrap">
        {script ? (
          highlightAnnotations(script)
        ) : (
          <span className="italic">No script</span>
        )}
      </div>
      <div className="mt-3 space-y-1 text-sm text-muted-foreground">
        <div className="flex justify-between">
          <span>Visual cues:</span>
          <span>{segmentCount}</span>
        </div>
        <div className="flex justify-between">
          <span>Voice:</span>
          <span className="capitalize">{voice}</span>
        </div>
        <div className="flex justify-between">
          <span>Style:</span>
          <span className="capitalize">{style}</span>
        </div>
      </div>
    </div>
  )
}

/** Render script text with highlighted [annotations]. */
function highlightAnnotations(text: string) {
  const parts = text.split(/(\[[^\]]+\])/g)
  return parts.map((part, i) => {
    if (part.startsWith('[') && part.endsWith(']')) {
      return (
        <span key={i} className="text-primary font-medium">
          {part}
        </span>
      )
    }
    return <span key={i}>{part}</span>
  })
}
