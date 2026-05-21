/**
 * Generic SceneEditor — works for ALL scene-based templates.
 *
 * Detects the template's plugin_id and renders the appropriate sidebar
 * panel (music video, prompt-to-video, script-to-video) while sharing
 * the common scene grid, workflow progress bar, and export modal.
 */

import { useState, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  RefreshCw, ChevronLeft, Image, Video, Download,
  CheckCircle, Clock, AlertCircle, Trash2, Plus,
} from 'lucide-react'
import {
  jobsApi, scenesApi, type VideoScene, type SceneUpdate,
  type Template,
} from '../api/client'
import { Button } from '../components/ui/button'
import { SceneEditModal } from '../components/SceneEditModal'
import { ExportModal } from '../components/ExportModal'

// ── Plugin-specific sidebar panels ─────────────────────────────────

import { MusicVideoPanel } from './editor/MusicVideoPanel'
import { PromptToVideoPanel } from './editor/PromptToVideoPanel'
import { ScriptToVideoPanel } from './editor/ScriptToVideoPanel'

// ── Shared constants ───────────────────────────────────────────────

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

function formatTime(seconds: number) {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

// ── Main Component ─────────────────────────────────────────────────

export default function SceneEditor() {
  const { jobId } = useParams<{ jobId: string }>()
  const queryClient = useQueryClient()

  const [editingScene, setEditingScene] = useState<VideoScene | null>(null)
  const [showExportModal, setShowExportModal] = useState(false)

  // ── Data fetching ─────────────────────────────────────────────────

  const { data: job, isLoading: jobLoading } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => jobsApi.get(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const j = query.state.data
      if (j && ['processing', 'pending'].includes(j.status)) return 3000
      return false
    },
  })

  // Resolve template → plugin_id
  const pluginId = useMemo(() => {
    // We'll load the template to read plugin_id from config
    return job?.input_data?.plugin_id as string | undefined
  }, [job])

  const { data: template } = useQuery({
    queryKey: ['template', job?.template_id],
    queryFn: async () => {
      if (!job?.template_id) return null
      const res = await fetch(`/api/templates/${job.template_id}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      })
      return res.json() as Promise<Template>
    },
    enabled: !!job?.template_id,
  })

  const resolvedPluginId = pluginId || (template?.config?.plugin_id as string) || 'music_video'

  const { data: scenes, isLoading: scenesLoading, refetch: refetchScenes } = useQuery({
    queryKey: ['scenes', jobId],
    queryFn: () => scenesApi.listScenes(jobId!),
    enabled: !!jobId,
    refetchInterval: () => {
      const j = queryClient.getQueryData<{ status?: string }>(['job', jobId])
      if (j?.status === 'processing') return 3000
      return false
    },
  })

  const { data: exportOptions } = useQuery({
    queryKey: ['exportOptions', jobId],
    queryFn: () => scenesApi.getExportOptions(jobId!),
    enabled: !!jobId && job?.stage === 'videos_ready',
  })

  // ── Mutations ─────────────────────────────────────────────────────

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

  const createSceneMutation = useMutation({
    mutationFn: () => scenesApi.createScene(jobId!),
    onSuccess: () => refetchScenes(),
  })

  const deleteSceneMutation = useMutation({
    mutationFn: (sceneId: string) => scenesApi.deleteScene(jobId!, sceneId),
    onSuccess: () => refetchScenes(),
  })

  // ── Helpers ───────────────────────────────────────────────────────

  const getStageIndex = (stage: string) =>
    WORKFLOW_STAGES.findIndex(s => s.id === stage)

  const getCurrentStageLabel = () => {
    const stage = job?.stage || 'planning'
    return WORKFLOW_STAGES.find(s => s.id === stage)?.label || stage
  }

  const canGenerateImages = () =>
    !!job?.stage && ['planned', 'images_ready'].includes(job.stage)

  const canGenerateVideos = () =>
    !!job?.stage && ['images_ready', 'videos_ready'].includes(job.stage)

  const allVideosGenerated = () =>
    !!scenes?.length && scenes.every(s => s.generated_video_path)

  const isPlanningStage = () =>
    job?.stage === 'planning' || (!scenesLoading && (!scenes || scenes.length === 0))

  // ── Loading state ─────────────────────────────────────────────────

  if (jobLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <RefreshCw className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  // ── Render ────────────────────────────────────────────────────────

  return (
    <div className="container mx-auto p-6">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <Button variant="ghost" onClick={() => window.history.back()}>
          <ChevronLeft className="h-4 w-4 mr-2" />
          Back
        </Button>
        <h1 className="text-2xl font-bold">
          {resolvedPluginId === 'music_video' && 'Music Video Editor'}
          {resolvedPluginId === 'prompt_to_video' && 'Prompt to Video Editor'}
          {resolvedPluginId === 'script_to_video' && 'Script to Video Editor'}
          {!['music_video', 'prompt_to_video', 'script_to_video'].includes(resolvedPluginId) && 'Scene Editor'}
        </h1>
      </div>

      {/* Workflow Progress Bar */}
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
                  <div
                    className={`w-8 h-0.5 mx-1 ${
                      index < currentIndex ? 'bg-green-500' : 'bg-muted'
                    }`}
                  />
                )}
              </div>
            )
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Main content area */}
        <div className="lg:col-span-3 space-y-6">
          {isPlanningStage() ? (
            /* Planning phase: delegate to plugin-specific panel */
            renderPlanningPanel(resolvedPluginId)
          ) : (
            /* Scene grid */
            <>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">
                  Timeline ({scenes?.length || 0} scenes)
                </h2>
                <div className="flex gap-2 flex-wrap">
                  {canGenerateImages() && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => generateAllImagesMutation.mutate()}
                      disabled={generateAllImagesMutation.isPending}
                    >
                      <Image className="h-4 w-4 mr-2" />
                      {generateAllImagesMutation.isPending ? 'Generating...' : 'Generate All Images'}
                    </Button>
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
                    <Button size="sm" onClick={() => setShowExportModal(true)}>
                      <Download className="h-4 w-4 mr-2" />
                      Export Video
                    </Button>
                  )}
                </div>
              </div>

              {/* Scene list */}
              <div className="bg-card rounded-lg border p-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold">Scenes ({scenes?.length || 0})</h3>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => createSceneMutation.mutate()}
                    disabled={createSceneMutation.isPending}
                    title="Add a new scene at the end"
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    Add Scene
                  </Button>
                </div>

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
                              <p className="text-sm mb-2 italic">&ldquo;{scene.lyrics_segment}&rdquo;</p>
                            )}
                            {scene.visual_description && (
                              <p className="text-sm text-muted-foreground">
                                {scene.visual_description}
                              </p>
                            )}
                            {scene.image_prompt && (
                              <p className="text-xs text-muted-foreground mt-1">
                                Prompt: {scene.image_prompt.substring(0, 100)}
                                {scene.image_prompt.length > 100 ? '...' : ''}
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
                                title="Generate image for this scene"
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
                                title="Generate video for this scene"
                              >
                                <Video className="h-4 w-4" />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setEditingScene(scene)}
                              title="Edit scene"
                            >
                              <RefreshCw className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                if (confirm('Delete this scene?'))
                                  deleteSceneMutation.mutate(scene.id)
                              }}
                              disabled={deleteSceneMutation.isPending}
                              className="text-destructive hover:text-destructive"
                              title="Delete scene"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>

                        {/* Status indicators */}
                        <div className="flex items-center gap-4 mt-2">
                          <div className="flex items-center gap-2">
                            {scene.reference_image_path ? (
                              <span className="flex items-center gap-1 text-xs text-green-600">
                                <CheckCircle className="h-3 w-3" /> Image Ready
                              </span>
                            ) : scene.status === 'generating_image' ? (
                              <span className="flex items-center gap-1 text-xs text-yellow-600">
                                <Clock className="h-3 w-3" /> Generating...
                              </span>
                            ) : (
                              <span className="text-xs text-muted-foreground">No image</span>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            {scene.generated_video_path ? (
                              <span className="flex items-center gap-1 text-xs text-green-600">
                                <CheckCircle className="h-3 w-3" /> Video Ready
                              </span>
                            ) : scene.status === 'generating_video' ? (
                              <span className="flex items-center gap-1 text-xs text-yellow-600">
                                <Clock className="h-3 w-3" /> Generating...
                              </span>
                            ) : (
                              <span className="text-xs text-muted-foreground">No video</span>
                            )}
                          </div>
                        </div>

                        {/* Thumbnail */}
                        {scene.reference_image_path && (
                          <div className="mt-2">
                            <img
                              src={`/api/uploads/stream/${scene.reference_image_path}`}
                              alt={`Scene ${index + 1}`}
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
                  onClick={() =>
                    scenesApi.planScenes(jobId!, {
                      lyrics_data: (job?.input_data?.lyrics as Record<string, unknown>) || {},
                      duration: 30,
                      style: (job?.input_data?.style as string) || 'realistic',
                    }).then(() => {
                      refetchScenes()
                      queryClient.invalidateQueries({ queryKey: ['job', jobId] })
                    })
                  }
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
            </>
          )}
        </div>

        {/* Sidebar: plugin-specific panel */}
        <div className="space-y-4">
          {resolvedPluginId === 'music_video' && (
            <MusicVideoPanel job={job} jobId={jobId!} scenes={scenes} />
          )}
          {resolvedPluginId === 'prompt_to_video' && (
            <PromptToVideoPanel job={job} jobId={jobId!} scenes={scenes} />
          )}
          {resolvedPluginId === 'script_to_video' && (
            <ScriptToVideoPanel job={job} jobId={jobId!} scenes={scenes} />
          )}

          {/* Common job status sidebar */}
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

      {/* Modals */}
      {editingScene && (
        <SceneEditModal
          scene={editingScene}
          onClose={() => setEditingScene(null)}
          onSave={(updates) => {
            const cleanUpdates: SceneUpdate = {}
            if (updates.lyrics_segment !== undefined)
              cleanUpdates.lyrics_segment = updates.lyrics_segment ?? undefined
            if (updates.visual_description !== undefined)
              cleanUpdates.visual_description = updates.visual_description ?? undefined
            if (updates.image_prompt !== undefined)
              cleanUpdates.image_prompt = updates.image_prompt ?? undefined
            if (updates.mood !== undefined) cleanUpdates.mood = updates.mood
            if (updates.camera_movement !== undefined)
              cleanUpdates.camera_movement = updates.camera_movement
            if (updates.start_time !== undefined) cleanUpdates.start_time = updates.start_time
            if (updates.end_time !== undefined) cleanUpdates.end_time = updates.end_time
            if (updates.reference_image_path !== undefined)
              cleanUpdates.reference_image_path = updates.reference_image_path ?? undefined
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

  // ── Planning panel router ────────────────────────────────────────

  function renderPlanningPanel(pid: string) {
    if (pid === 'music_video') {
      return (
        <MusicVideoPanel
          job={job}
          jobId={jobId!}
          scenes={scenes}
          planningMode
        />
      )
    }
    if (pid === 'prompt_to_video') {
      return (
        <PromptToVideoPanel
          job={job}
          jobId={jobId!}
          scenes={scenes}
          planningMode
        />
      )
    }
    if (pid === 'script_to_video') {
      return (
        <ScriptToVideoPanel
          job={job}
          jobId={jobId!}
          scenes={scenes}
          planningMode
        />
      )
    }
    // Generic fallback
    return (
      <div className="bg-card rounded-lg border p-6">
        <h2 className="text-lg font-semibold mb-4">Configure Your Video</h2>
        <p className="text-muted-foreground">
          Job is being planned. Check back shortly.
        </p>
      </div>
    )
  }
}
