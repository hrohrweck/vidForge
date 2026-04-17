import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  RefreshCw, ChevronLeft, Image, Video, Download, CheckCircle, Clock, AlertCircle 
} from 'lucide-react'
import { jobsApi, scenesApi, VideoScene, SceneUpdate } from '../api/client'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { SceneEditModal } from '../components/SceneEditModal'
import { ExportModal } from '../components/ExportModal'

interface LyricsData {
  lyrics: { text: string; start: number; end: number }[]
  lines: { text: string; start: number; end: number }[]
  full_text: string
  duration: number
}

const WORKFLOW_STAGES = [
  { id: 'planning', label: 'Planning', icon: Clock },
  { id: 'planned', label: 'Planned', icon: CheckCircle },
  { id: 'generating_images', label: 'Generating Images', icon: Image },
  { id: 'images_ready', label: 'Images Ready', icon: CheckCircle },
  { id: 'generating_videos', label: 'Generating Videos', icon: Video },
  { id: 'videos_ready', label: 'Videos Ready', icon: CheckCircle },
  { id: 'rendering', label: 'Rendering', icon: Clock },
  { id: 'completed', label: 'Completed', icon: CheckCircle },
] as const

export default function MusicVideoEditor() {
  const { jobId } = useParams<{ jobId: string }>()
  const queryClient = useQueryClient()

  const [editingScene, setEditingScene] = useState<VideoScene | null>(null)
  const [showExportModal, setShowExportModal] = useState(false)
  const [lyricsMode, setLyricsMode] = useState<'auto' | 'manual'>('auto')
  const [manualLyrics, setManualLyrics] = useState('')
  const [duration, setDuration] = useState(30)
  const [style, setStyle] = useState('realistic')

  const { data: job, isLoading: jobLoading } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => jobsApi.get(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const job = query.state.data
      if (job && ['processing', 'pending'].includes(job.status)) {
        return 3000
      }
      return false
    },
  })

  const { data: scenes, isLoading: scenesLoading, refetch: refetchScenes } = useQuery({
    queryKey: ['scenes', jobId],
    queryFn: () => scenesApi.listScenes(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const job = query.state.data?.[0]?.job_id
      if (job) {
        const jobData = queryClient.getQueryData(['job', jobId]) as { status?: string } | undefined
        if (jobData?.status === 'processing') {
          return 3000
        }
      }
      return false
    },
  })

  const { data: exportOptions } = useQuery({
    queryKey: ['exportOptions', jobId],
    queryFn: () => scenesApi.getExportOptions(jobId!),
    enabled: !!jobId && job?.stage === 'videos_ready',
  })

  const extractLyricsMutation = useMutation({
    mutationFn: () => {
      const audioFile = (job?.input_data?.audio_file as string) || ''
      return scenesApi.extractLyrics(jobId!, { audio_file_path: audioFile })
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
      return scenesApi.planScenes(jobId!, {
        lyrics_data: lyrics,
        duration,
        style,
      })
    },
    onSuccess: () => {
      refetchScenes()
      queryClient.invalidateQueries({ queryKey: ['job', jobId] })
    },
  })

  const regeneratePromptsMutation = useMutation({
    mutationFn: () => planScenesMutation.mutateAsync(),
    onSuccess: () => refetchScenes(),
  })

  const updateSceneMutation = useMutation({
    mutationFn: ({ sceneId, updates }: { sceneId: string; updates: SceneUpdate }) =>
      scenesApi.updateScene(jobId!, sceneId, updates),
    onSuccess: () => refetchScenes(),
  })

  const generateImageMutation = useMutation({
    mutationFn: (sceneId: string) => scenesApi.generateImage(jobId!, sceneId),
    onSuccess: () => refetchScenes(),
  })

  const generateVideoMutation = useMutation({
    mutationFn: (sceneId: string) => scenesApi.generateVideo(jobId!, sceneId),
    onSuccess: () => refetchScenes(),
  })

  const generateAllImagesMutation = useMutation({
    mutationFn: () => scenesApi.generateAllImages(jobId!),
    onSuccess: () => {
      refetchScenes()
      queryClient.invalidateQueries({ queryKey: ['job', jobId] })
    },
  })

  const generateAllVideosMutation = useMutation({
    mutationFn: () => scenesApi.generateAllVideos(jobId!),
    onSuccess: () => {
      refetchScenes()
      queryClient.invalidateQueries({ queryKey: ['job', jobId] })
    },
  })

  const handleManualLyricsSubmit = async () => {
    try {
      await scenesApi.setManualLyrics(jobId!, { lyrics_text: manualLyrics, duration })
      const lyrics = { full_text: manualLyrics, duration }
      queryClient.setQueryData(['job', jobId], {
        ...job,
        input_data: { ...job?.input_data, lyrics },
      })
    } catch (error) {
      console.error('Failed to set manual lyrics:', error)
    }
  }

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const getStageIndex = (stage: string) => {
    return WORKFLOW_STAGES.findIndex(s => s.id === stage)
  }

  const getCurrentStageLabel = () => {
    const stage = job?.stage || 'planning'
    return WORKFLOW_STAGES.find(s => s.id === stage)?.label || stage
  }

  const canGenerateImages = () => {
    const stage = job?.stage
    return stage && ['planned', 'images_ready'].includes(stage)
  }

  const canGenerateVideos = () => {
    const stage = job?.stage
    return stage && ['images_ready', 'videos_ready'].includes(stage)
  }

  const allVideosGenerated = () => {
    if (!scenes || scenes.length === 0) return false
    return scenes.every(s => s.generated_video_path)
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
      </div>

      <div className="bg-card rounded-lg border p-4 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Workflow Progress</h2>
          <span className="text-sm font-medium text-primary">
            Current Stage: {getCurrentStageLabel()}
          </span>
        </div>
        <div className="flex items-center gap-2 overflow-x-auto">
          {WORKFLOW_STAGES.map((stage, index) => {
            const currentIndex = getStageIndex(job?.stage || 'planning')
            const isActive = index <= currentIndex
            const isCurrent = stage.id === job?.stage
            const Icon = stage.icon
            
            return (
              <div key={stage.id} className="flex items-center">
                <div
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${
                    isCurrent
                      ? 'bg-primary text-primary-foreground'
                      : isActive
                      ? 'bg-green-100 text-green-800'
                      : 'bg-muted text-muted-foreground'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span>{stage.label}</span>
                </div>
                {index < WORKFLOW_STAGES.length - 1 && (
                  <div className={`w-8 h-0.5 mx-1 ${
                    index < currentIndex ? 'bg-green-500' : 'bg-muted'
                  }`} />
                )}
              </div>
            )
          })}
        </div>
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
                          <option value="cinematic">Cinematic</option>
                          <option value="abstract">Abstract</option>
                        </select>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        onClick={() => extractLyricsMutation.mutate()}
                        disabled={extractLyricsMutation.isPending || !job?.input_data?.audio_file}
                      >
                        {extractLyricsMutation.isPending ? 'Extracting...' : 'Extract Lyrics from Audio'}
                      </Button>
                      {!!job?.input_data?.lyrics && (
                        <Button onClick={() => planScenesMutation.mutate()} disabled={planScenesMutation.isPending}>
                          {planScenesMutation.isPending ? 'Planning...' : 'Generate Scene Plan'}
                        </Button>
                      )}
                    </div>
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
                          <option value="cinematic">Cinematic</option>
                          <option value="abstract">Abstract</option>
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
                    <div className="flex gap-2">
                      <Button onClick={handleManualLyricsSubmit}>Set Lyrics</Button>
                      {!!job?.input_data?.lyrics && (
                        <Button onClick={() => planScenesMutation.mutate()} disabled={planScenesMutation.isPending}>
                          {planScenesMutation.isPending ? 'Planning...' : 'Generate Scene Plan'}
                        </Button>
                      )}
                    </div>
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
                <div className="flex gap-2 flex-wrap">
                  {canGenerateImages() && (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => generateAllImagesMutation.mutate()}
                        disabled={generateAllImagesMutation.isPending}
                      >
                        <Image className="h-4 w-4 mr-2" />
                        {generateAllImagesMutation.isPending ? 'Generating...' : 'Generate All Images'}
                      </Button>
                    </>
                  )}
                  {canGenerateVideos() && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => generateAllVideosMutation.mutate()}
                      disabled={generateAllVideosMutation.isPending}
                    >
                      <Video className="h-4 w-4 mr-2" />
                      {generateAllVideosMutation.isPending ? 'Generating...' : 'Generate All Videos'}
                    </Button>
                  )}
                  {allVideosGenerated() && (
                    <Button
                      size="sm"
                      onClick={() => setShowExportModal(true)}
                    >
                      <Download className="h-4 w-4 mr-2" />
                      Export Video
                    </Button>
                  )}
                </div>
              </div>

              <div className="bg-card rounded-lg border p-4">
                <div className="space-y-4">
                  {scenes?.map((scene: VideoScene, index: number) => (
                    <div key={scene.id} className="flex items-start gap-4 p-4 border rounded-lg">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-medium">
                        {index + 1}
                      </div>
                      <div className="flex-grow min-w-0">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-grow">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-sm text-muted-foreground">
                                {formatTime(scene.start_time)} - {formatTime(scene.end_time)}
                              </span>
                              {scene.status === 'error' && (
                                <span className="flex items-center gap-1 text-xs text-red-500">
                                  <AlertCircle className="h-3 w-3" />
                                  {scene.error_message || 'Error'}
                                </span>
                              )}
                            </div>
                            {scene.lyrics_segment && (
                              <p className="text-sm mb-2 italic">"{scene.lyrics_segment}"</p>
                            )}
                            {scene.visual_description && (
                              <p className="text-sm text-muted-foreground">{scene.visual_description}</p>
                            )}
                            {scene.image_prompt && (
                              <p className="text-xs text-muted-foreground mt-1">
                                Prompt: {scene.image_prompt.substring(0, 100)}...
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            {!scene.reference_image_path && canGenerateImages() && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => generateImageMutation.mutate(scene.id)}
                                disabled={generateImageMutation.isPending}
                              >
                                <Image className="h-4 w-4" />
                              </Button>
                            )}
                            {scene.reference_image_path && !scene.generated_video_path && canGenerateVideos() && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => generateVideoMutation.mutate(scene.id)}
                                disabled={generateVideoMutation.isPending}
                              >
                                <Video className="h-4 w-4" />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setEditingScene(scene)}
                            >
                              <RefreshCw className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                        
                        <div className="flex items-center gap-4 mt-2">
                          <div className="flex items-center gap-2">
                            {scene.reference_image_path ? (
                              <span className="flex items-center gap-1 text-xs text-green-600">
                                <CheckCircle className="h-3 w-3" />
                                Image Ready
                              </span>
                            ) : scene.status === 'generating_image' ? (
                              <span className="flex items-center gap-1 text-xs text-yellow-600">
                                <Clock className="h-3 w-3" />
                                Generating...
                              </span>
                            ) : (
                              <span className="text-xs text-muted-foreground">No image</span>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            {scene.generated_video_path ? (
                              <span className="flex items-center gap-1 text-xs text-green-600">
                                <CheckCircle className="h-3 w-3" />
                                Video Ready
                              </span>
                            ) : scene.status === 'generating_video' ? (
                              <span className="flex items-center gap-1 text-xs text-yellow-600">
                                <Clock className="h-3 w-3" />
                                Generating...
                              </span>
                            ) : (
                              <span className="text-xs text-muted-foreground">No video</span>
                            )}
                          </div>
                        </div>

                        {scene.reference_image_path && (
                          <div className="mt-2">
                            <img
                              src={`/api/uploads/${scene.reference_image_path}`}
                              alt={`Scene ${index + 1} reference`}
                              className="h-20 object-cover rounded border"
                            />
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between">
                <Button
                  variant="outline"
                  onClick={() => regeneratePromptsMutation.mutate()}
                  disabled={regeneratePromptsMutation.isPending || planScenesMutation.isPending}
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Regenerate Prompts
                </Button>
                {allVideosGenerated() && (
                  <Button onClick={() => setShowExportModal(true)}>
                    <Download className="h-4 w-4 mr-2" />
                    Export Final Video
                  </Button>
                )}
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

          <div className="bg-card rounded-lg border p-4">
            <h3 className="font-semibold mb-2">Job Status</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Status:</span>
                <span className="font-medium">{job?.status || 'Unknown'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Progress:</span>
                <span className="font-medium">{job?.progress || 0}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Scenes:</span>
                <span className="font-medium">{scenes?.length || 0}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {editingScene && (
        <SceneEditModal
          scene={editingScene}
          onClose={() => setEditingScene(null)}
          onSave={(updates) => {
            const cleanUpdates: SceneUpdate = {}
            if (updates.lyrics_segment !== undefined) cleanUpdates.lyrics_segment = updates.lyrics_segment ?? undefined
            if (updates.visual_description !== undefined) cleanUpdates.visual_description = updates.visual_description ?? undefined
            if (updates.image_prompt !== undefined) cleanUpdates.image_prompt = updates.image_prompt ?? undefined
            if (updates.mood !== undefined) cleanUpdates.mood = updates.mood
            if (updates.camera_movement !== undefined) cleanUpdates.camera_movement = updates.camera_movement
            if (updates.start_time !== undefined) cleanUpdates.start_time = updates.start_time
            if (updates.end_time !== undefined) cleanUpdates.end_time = updates.end_time
            if (updates.reference_image_path !== undefined) cleanUpdates.reference_image_path = updates.reference_image_path ?? undefined
            updateSceneMutation.mutate({ sceneId: editingScene.id, updates: cleanUpdates })
            setEditingScene(null)
          }}
        />
      )}

      {showExportModal && jobId && (
        <ExportModal
          jobId={jobId}
          exportOptions={exportOptions}
          onClose={() => setShowExportModal(false)}
          onExported={() => {
            setShowExportModal(false)
            queryClient.invalidateQueries({ queryKey: ['job', jobId] })
          }}
        />
      )}
    </div>
  )
}
