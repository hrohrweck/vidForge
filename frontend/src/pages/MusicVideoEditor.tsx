import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Play, RefreshCw, ChevronLeft } from 'lucide-react'
import { jobsApi } from '../api/client'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { SceneCard } from '../components/SceneCard'
import { SceneEditModal } from '../components/SceneEditModal'

interface LyricsData {
  lyrics: { text: string; start: number; end: number }[]
  lines: { text: string; start: number; end: number }[]
  full_text: string
  duration: number
}

interface Scene {
  id: string
  job_id: string
  scene_number: number
  start_time: number
  end_time: number
  lyrics_segment: string | null
  visual_description: string | null
  image_prompt: string | null
  mood: string
  camera_movement: string
  reference_image_path: string | null
  thumbnail_path: string | null
  generated_video_path: string | null
  status: string
}

const scenesApi = {
  get: async (jobId: string) => {
    const response = await fetch(`/api/jobs/${jobId}/scenes`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
    })
    if (!response.ok) throw new Error('Failed to fetch scenes')
    return response.json()
  },
  extractLyrics: async (jobId: string, audioFilePath: string) => {
    const response = await fetch(`/api/jobs/${jobId}/lyrics/extract`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('token')}`,
      },
      body: JSON.stringify({ audio_file_path: audioFilePath }),
    })
    if (!response.ok) throw new Error('Failed to extract lyrics')
    return response.json()
  },
  setManualLyrics: async (jobId: string, lyricsText: string, duration: number) => {
    const response = await fetch(`/api/jobs/${jobId}/lyrics/manual`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('token')}`,
      },
      body: JSON.stringify({ lyrics_text: lyricsText, duration }),
    })
    if (!response.ok) throw new Error('Failed to set lyrics')
    return response.json()
  },
  planScenes: async (jobId: string, lyricsData: LyricsData, duration: number, style: string) => {
    const response = await fetch(`/api/jobs/${jobId}/scenes/plan`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('token')}`,
      },
      body: JSON.stringify({ lyrics_data: lyricsData, duration, style }),
    })
    if (!response.ok) throw new Error('Failed to plan scenes')
    return response.json()
  },
  updateScene: async (jobId: string, sceneId: string, updates: Partial<Scene>) => {
    const response = await fetch(`/api/jobs/${jobId}/scenes/${sceneId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('token')}`,
      },
      body: JSON.stringify(updates),
    })
    if (!response.ok) throw new Error('Failed to update scene')
    return response.json()
  },
  deleteScene: async (jobId: string, sceneId: string) => {
    const response = await fetch(`/api/jobs/${jobId}/scenes/${sceneId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
    })
    if (!response.ok) throw new Error('Failed to delete scene')
    return response.json()
  },
  regeneratePrompts: async (jobId: string) => {
    const response = await fetch(`/api/jobs/${jobId}/scenes/regenerate-prompts`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
    })
    if (!response.ok) throw new Error('Failed to regenerate prompts')
    return response.json()
  },
  updateStage: async (jobId: string, stage: string) => {
    const response = await fetch(`/api/jobs/${jobId}/stage`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('token')}`,
      },
      body: JSON.stringify({ stage }),
    })
    if (!response.ok) throw new Error('Failed to update stage')
    return response.json()
  },
}

export default function MusicVideoEditor() {
  const { jobId } = useParams<{ jobId: string }>()
  const queryClient = useQueryClient()

  const [editingScene, setEditingScene] = useState<Scene | null>(null)
  const [lyricsMode, setLyricsMode] = useState<'auto' | 'manual'>('auto')
  const [manualLyrics, setManualLyrics] = useState('')
  const [duration, setDuration] = useState(30)
  const [style, setStyle] = useState('realistic')

  const { data: job, isLoading: jobLoading } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => jobsApi.get(jobId!),
    enabled: !!jobId,
  })

  const { data: scenes, isLoading: scenesLoading, refetch: refetchScenes } = useQuery({
    queryKey: ['scenes', jobId],
    queryFn: () => scenesApi.get(jobId!),
    enabled: !!jobId,
  })

  const extractLyricsMutation = useMutation({
    mutationFn: () => scenesApi.extractLyrics(jobId!, (job?.input_data?.audio_file as string) || ''),
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
      const lyrics = job?.input_data?.lyrics as LyricsData | undefined
      if (!lyrics) throw new Error('No lyrics available')
      return scenesApi.planScenes(jobId!, lyrics, duration, style)
    },
    onSuccess: () => refetchScenes(),
  })

  const regeneratePromptsMutation = useMutation({
    mutationFn: () => scenesApi.regeneratePrompts(jobId!),
    onSuccess: () => refetchScenes(),
  })

  const updateSceneMutation = useMutation({
    mutationFn: ({ sceneId, updates }: { sceneId: string; updates: Partial<Scene> }) =>
      scenesApi.updateScene(jobId!, sceneId, updates),
    onSuccess: () => refetchScenes(),
  })

  const generatePreviewsMutation = useMutation({
    mutationFn: async () => {
      for (const scene of scenes || []) {
        await fetch(`/api/jobs/${jobId}/scenes/${scene.id}/generate-preview`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
        })
      }
    },
    onSuccess: () => refetchScenes(),
  })

  const renderFinalMutation = useMutation({
    mutationFn: () => scenesApi.updateStage(jobId!, 'rendering'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['job', jobId] })
    },
  })

  const handleManualLyricsSubmit = async () => {
    try {
      await scenesApi.setManualLyrics(jobId!, manualLyrics, duration)
      const lyrics = { full_text: manualLyrics, duration }
      queryClient.setQueryData(['job', jobId], {
        ...job,
        input_data: { ...job?.input_data, lyrics },
      })
    } catch (error) {
      console.error('Failed to set manual lyrics:', error)
    }
  }

  const handlePlanScenes = () => {
    planScenesMutation.mutate()
  }

  const handleRegeneratePrompts = () => {
    regeneratePromptsMutation.mutate()
  }

  const handleGeneratePreviews = () => {
    generatePreviewsMutation.mutate()
  }

  const handleRenderFinal = () => {
    renderFinalMutation.mutate()
  }

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  if (jobLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <RefreshCw className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  return (
    <div className="container mx-auto p-6">
      <div className="flex items-center gap-4 mb-6">
        <Button variant="ghost" onClick={() => window.history.back()}>
          <ChevronLeft className="h-4 w-4 mr-2" />
          Back
        </Button>
        <h1 className="text-2xl font-bold">Music Video Editor</h1>
        <span className="text-sm text-muted-foreground">
          Stage: {job?.stage || 'planning'}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-3 space-y-6">
          {!scenesLoading && (!scenes || scenes.length === 0) ? (
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

                {lyricsMode === 'auto' ? (
                  <div className="space-y-4">
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
                        </select>
                      </div>
                    </div>
                    <Button
                      onClick={() => extractLyricsMutation.mutate()}
                      disabled={extractLyricsMutation.isPending || !job?.input_data?.audio_file}
                    >
                      {extractLyricsMutation.isPending ? 'Extracting...' : 'Extract Lyrics from Audio'}
                    </Button>
                    {!!job?.input_data?.lyrics && (
                      <Button onClick={handlePlanScenes} disabled={planScenesMutation.isPending}>
                        {planScenesMutation.isPending ? 'Planning...' : 'Generate Scene Plan'}
                      </Button>
                    )}
                  </div>
                ) : (
                  <div className="space-y-4">
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
                        </select>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label>Lyrics</Label>
                      <textarea
                        className="w-full h-40 rounded-md border border-input bg-background px-3 py-2"
                        value={manualLyrics}
                        onChange={(e) => setManualLyrics(e.target.value)}
                        placeholder="Paste lyrics here (each line will be treated as a line in the song)"
                      />
                    </div>
                    <Button onClick={handleManualLyricsSubmit}>Set Lyrics</Button>
                    {!!job?.input_data?.lyrics && (
                      <Button onClick={handlePlanScenes} disabled={planScenesMutation.isPending}>
                        {planScenesMutation.isPending ? 'Planning...' : 'Generate Scene Plan'}
                      </Button>
                    )}
                  </div>
                )}

                {!!job?.input_data?.lyrics && (
                  <div className="mt-4 p-4 bg-muted rounded-lg">
                    <h3 className="font-medium mb-2">Extracted Lyrics</h3>
                    <p className="text-sm text-muted-foreground">
                      {(job.input_data.lyrics as LyricsData).full_text?.substring(0, 200)}...
                    </p>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Timeline ({scenes?.length || 0} scenes)</h2>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleRegeneratePrompts}
                    disabled={regeneratePromptsMutation.isPending}
                  >
                    <RefreshCw className={`h-4 w-4 mr-2 ${regeneratePromptsMutation.isPending ? 'animate-spin' : ''}`} />
                    Regenerate Prompts
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleGeneratePreviews}
                    disabled={generatePreviewsMutation.isPending}
                  >
                    Generate Previews
                  </Button>
                  <Button onClick={handleRenderFinal} disabled={renderFinalMutation.isPending}>
                    <Play className="h-4 w-4 mr-2" />
                    Render Final Video
                  </Button>
                </div>
              </div>

              <div className="bg-card rounded-lg border p-4">
                <div className="flex gap-2 overflow-x-auto pb-2">
                  {scenes?.map((scene: Scene, index: number) => (
                    <SceneCard
                      key={scene.id}
                      scene={scene}
                      index={index}
                      onEdit={() => setEditingScene(scene)}
                      formatTime={formatTime}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="bg-card rounded-lg border p-4">
            <h3 className="font-semibold mb-2">Audio</h3>
            {!!job?.input_data?.audio_file && (
              <audio controls className="w-full" src={`/api/uploads/${job.input_data.audio_file}`}>
                Your browser does not support audio.
              </audio>
            )}
          </div>

          <div className="bg-card rounded-lg border p-4">
            <h3 className="font-semibold mb-2">Lyrics</h3>
            {!!job?.input_data?.lyrics && (
              <div className="text-sm text-muted-foreground max-h-60 overflow-y-auto">
                {(job.input_data.lyrics as LyricsData).lines?.map((line: { text: string; start: number }, i: number) => (
                  <div key={i} className="py-1">
                    <span className="text-xs text-muted-foreground mr-2">
                      {formatTime(line.start)}
                    </span>
                    {line.text}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {editingScene && (
        <SceneEditModal
          scene={editingScene}
          onClose={() => setEditingScene(null)}
          onSave={(updates) => {
            updateSceneMutation.mutate({ sceneId: editingScene.id, updates })
            setEditingScene(null)
          }}
        />
      )}
    </div>
  )
}
