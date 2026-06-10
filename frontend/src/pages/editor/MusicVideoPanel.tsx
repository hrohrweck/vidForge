/**
 * Music Video sidebar panel + planning form.
 *
 * Handles lyrics extraction, manual lyrics entry, and scene planning
 * for the music video template.
 */

import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { scenesApi, type Job, type VideoScene } from '../../api/client'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'

interface LyricsData {
  lyrics: { text: string; start: number; end: number }[]
  lines: { text: string; start: number; end: number }[]
  full_text: string
  duration: number
}

interface Props {
  job: Job | undefined
  jobId: string
  scenes: VideoScene[] | undefined
  planningMode?: boolean
}

export function MusicVideoPanel({ job, jobId, scenes, planningMode }: Props) {
  const queryClient = useQueryClient()

  const [lyricsMode, setLyricsMode] = useState<'auto' | 'manual'>('auto')
  const [manualLyrics, setManualLyrics] = useState('')
  const [duration, setDuration] = useState(30)
  const [style, setStyle] = useState(
    (job?.input_data?.style as string) || 'realistic',
  )
  const [audioUrl, setAudioUrl] = useState<string | null>(null)

  // Get audio duration
  useEffect(() => {
    if (job?.input_data?.audio_file && !job?.input_data?.lyrics) {
      scenesApi.getAudioMetadata(jobId).then((m) => setDuration(Math.round(m.duration))).catch(() => {})
    }
  }, [job?.input_data?.audio_file, job?.input_data?.lyrics, jobId])

  // Load audio blob for playback
  useEffect(() => {
    let objectUrl: string | null = null
    if (job?.input_data?.audio_file) {
      fetch(`/api/uploads/stream/${job.input_data.audio_file}`, {
        credentials: 'include',
      })
        .then((r) => (r.ok ? r.blob() : Promise.reject()))
        .then((blob) => {
          objectUrl = URL.createObjectURL(blob)
          setAudioUrl(objectUrl)
        })
        .catch(() => setAudioUrl(null))
    } else {
      setAudioUrl(null)
    }
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [job?.input_data?.audio_file])

  const extractLyricsMutation = useMutation({
    mutationFn: () => {
      const audioFile = (job?.input_data?.audio_file as string) || ''
      return scenesApi.extractLyrics(jobId, { audio_file_path: audioFile })
    },
    onSuccess: (data) => {
      if (job?.input_data) {
        queryClient.setQueryData(['job', jobId], {
          ...job,
          input_data: { ...job.input_data, lyrics: data.lyrics },
        })
      }
    },
  })

  const planScenesMutation = useMutation({
    mutationFn: () => {
      const lyrics = job?.input_data?.lyrics as Record<string, unknown> | undefined
      if (!lyrics) throw new Error('No lyrics available')
      return scenesApi.planScenes(jobId, { lyrics_data: lyrics, duration, style })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scenes', jobId] })
      queryClient.invalidateQueries({ queryKey: ['job', jobId] })
    },
  })

  const handleManualLyricsSubmit = async () => {
    try {
      await scenesApi.setManualLyrics(jobId, {
        lyrics_text: manualLyrics,
        duration,
      })
      const lyrics = { full_text: manualLyrics, duration }
      queryClient.setQueryData(['job', jobId], {
        ...job,
        input_data: { ...job?.input_data, lyrics },
      })
    } catch (err) {
      console.error('Failed to set manual lyrics:', err)
    }
  }

  // ── Planning mode: full planning form ─────────────────────────────

  if (planningMode) {
    return (
      <div className="lg:col-span-3">
        <div className="bg-card rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-4">Create Your Music Video</h2>
          <div className="space-y-4">
            <div className="flex gap-4">
              <Button
                variant={lyricsMode === 'auto' ? 'default' : 'outline'}
                onClick={() => setLyricsMode('auto')}
              >
                Auto-Extract Lyrics
              </Button>
              <Button
                variant={lyricsMode === 'manual' ? 'default' : 'outline'}
                onClick={() => setLyricsMode('manual')}
              >
                Enter Manually
              </Button>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Duration (seconds)</Label>
                <Input
                  type="number"
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                  min={5}
                  max={300}
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

            {lyricsMode === 'auto' ? (
              <div className="flex gap-2">
                <Button
                  onClick={() => extractLyricsMutation.mutate()}
                  disabled={extractLyricsMutation.isPending || !job?.input_data?.audio_file}
                >
                  {extractLyricsMutation.isPending ? 'Extracting...' : 'Extract Lyrics from Audio'}
                </Button>
                {!!job?.input_data?.lyrics && (
                  <Button
                    onClick={() => planScenesMutation.mutate()}
                    disabled={planScenesMutation.isPending || job?.stage === 'planning'}
                  >
                    {job?.stage === 'planning' ? 'Planning in Progress...' : planScenesMutation.isPending ? 'Planning...' : 'Generate Scene Plan'}
                  </Button>
                )}
              </div>
            ) : (
              <>
                <div className="space-y-2">
                  <Label>Lyrics</Label>
                  <textarea
                    className="w-full h-40 rounded-md border border-input bg-background px-3 py-2"
                    value={manualLyrics}
                    onChange={(e) => setManualLyrics(e.target.value)}
                    placeholder="Paste lyrics here..."
                  />
                </div>
                <div className="flex gap-2">
                  <Button onClick={handleManualLyricsSubmit}>Set Lyrics</Button>
                  {!!job?.input_data?.lyrics && (
                    <Button
                      onClick={() => planScenesMutation.mutate()}
                      disabled={planScenesMutation.isPending || job?.stage === 'planning'}
                    >
                      {job?.stage === 'planning' ? 'Planning in Progress...' : planScenesMutation.isPending ? 'Planning...' : 'Generate Scene Plan'}
                    </Button>
                  )}
                </div>
              </>
            )}

            {!!job?.input_data?.lyrics && (
              <div className="mt-4 p-4 bg-muted rounded-lg">
                <h3 className="font-medium mb-2">Extracted Lyrics</h3>
                <p className="text-sm text-muted-foreground">
                  {(job.input_data.lyrics as LyricsData).full_text?.substring(0, 200)}...
                </p>
              </div>
            )}

            {job?.stage === 'planning' && scenes && scenes.length > 0 && (
              <div className="mt-4 p-4 bg-primary/10 rounded-lg border border-primary/20">
                <p className="text-sm text-primary mb-2">
                  You have {scenes.length} scenes already planned. Continue to the scene editor or
                  regenerate.
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

  // ── Sidebar mode: audio player + lyrics display ───────────────────

  return (
    <>
      {/* Audio player */}
      <div className="bg-card rounded-lg border p-4">
        <h3 className="font-semibold mb-2">Audio</h3>
        {audioUrl ? (
          <audio key={audioUrl} controls className="w-full" src={audioUrl}>
            Your browser does not support audio.
          </audio>
        ) : job?.input_data?.audio_file ? (
          <div className="text-sm text-muted-foreground">Loading audio...</div>
        ) : null}
      </div>

      {/* Lyrics */}
      <div className="bg-card rounded-lg border p-4">
        <h3 className="font-semibold mb-2">Lyrics</h3>
        {!!job?.input_data?.lyrics && (
          <div className="text-sm text-muted-foreground max-h-60 overflow-y-auto">
            {(job.input_data.lyrics as LyricsData).lines?.map(
              (line: { text: string; start: number }, i: number) => (
                <div key={i} className="py-1">
                  <span className="text-xs text-muted-foreground mr-2">
                    {Math.floor(line.start / 60)}:{String(Math.floor(line.start % 60)).padStart(2, '0')}
                  </span>
                  {line.text}
                </div>
              ),
            )}
          </div>
        )}
      </div>
    </>
  )
}
