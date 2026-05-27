/**
 * Generic SceneEditor — works for ALL scene-based templates.
 *
 * Detects the template's plugin_id and renders the appropriate sidebar
 * panel (music video, prompt-to-video, script-to-video) while sharing
 * the common scene grid, workflow progress bar, and export modal.
 */

import { useState, useMemo, useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  RefreshCw, ChevronLeft, Image, Video, Download, Pencil,
  CheckCircle, Clock, AlertCircle, Trash2, Plus, Loader2, XCircle,
} from 'lucide-react'
import {
  jobsApi, scenesApi, templatesApi, modelsApi, type VideoScene, type SceneUpdate,
} from '../api/client'
import { cn } from '../lib/utils'
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

const ACTIVE_STAGES = new Set([
  'generating_images', 'generating_videos', 'rendering',
])

function formatTime(seconds: number) {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

// ── Main Component ─────────────────────────────────────────────────

export default function SceneEditor() {
  const { jobId } = useParams<{ jobId: string }>()
  const queryClient = useQueryClient()
  const hasPendingSceneOp = useRef(false)

  const [editingScene, setEditingScene] = useState<VideoScene | null>(null)
  const [showExportModal, setShowExportModal] = useState(false)
  const [pendingDownload, setPendingDownload] = useState(false)

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

  // Resolve template → plugin_id via the templates API
  const { data: template } = useQuery({
    queryKey: ['template', job?.template_id],
    queryFn: async () => {
      const resp = await templatesApi.get(job!.template_id!)
      return resp.data
    },
    enabled: !!job?.template_id,
  })

  // Plugin ID from template config, with smart fallback based on input_data
  const resolvedPluginId = useMemo(() => {
    if (template?.config?.plugin_id) return template.config.plugin_id as string
    // Fallback: infer from input_data before template loads
    const input = job?.input_data || {}
    if ('script' in input) return 'script_to_video'
    if ('prompt' in input && !('audio_file' in input)) return 'prompt_to_video'
    if ('audio_file' in input) return 'music_video'
    return 'music_video'
  }, [template?.config?.plugin_id, job?.input_data])

  const { data: scenes, isLoading: scenesLoading, refetch: refetchScenes } = useQuery({
    queryKey: ['scenes', jobId],
    queryFn: () => scenesApi.listScenes(jobId!),
    enabled: !!jobId,
    refetchInterval: () => {
      const j = queryClient.getQueryData<{ status?: string }>(['job', jobId])
      if (j?.status === 'processing') return 3000
      if (hasPendingSceneOp.current) return 2000
      return false
    },
  })

  const { data: exportOptions } = useQuery({
    queryKey: ['exportOptions', jobId],
    queryFn: () => scenesApi.getExportOptions(jobId!),
    enabled: !!jobId && job?.stage === 'videos_ready',
  })

  // ── Derived state ────────────────────────────────────────────────

  /** True when a background pipeline (images, videos, rendering) is running */
  const isOperationInProgress = useMemo(() => {
    const stage = job?.stage || ''
    return ACTIVE_STAGES.has(stage)
  }, [job?.stage])

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

  const cancelMutation = useMutation({
    mutationFn: () => scenesApi.cancel(jobId!),
    onSuccess: () => {
      refetchScenes()
      queryClient.invalidateQueries({ queryKey: ['job', jobId] })
    },
  })

  // ── Full regeneration (re-plan + images + videos) ─────────────────

  const [isRegenerating, setIsRegenerating] = useState(false)

  const regenerateAllMutation = useMutation({
    mutationFn: () => scenesApi.regenerateAll(jobId!),
    onSuccess: () => {
      setIsRegenerating(true)
      refetchScenes()
      queryClient.invalidateQueries({ queryKey: ['job', jobId] })
    },
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
    true  // Always allow per-scene video generation when image exists

  const allVideosGenerated = () =>
    !!scenes?.length && scenes.every(s => s.generated_video_path)

  const isPlanningStage = () =>
    job?.stage === 'planning' || (!scenesLoading && (!scenes || scenes.length === 0))

  // Detect when regeneration pipeline finishes
  useEffect(() => {
    if (isRegenerating && job?.status === 'completed') {
      setIsRegenerating(false)
      refetchScenes()
    }
  }, [isRegenerating, job?.status])

  // Auto-download after export completes
  useEffect(() => {
    if (pendingDownload && job?.status === 'completed' && job?.output_path) {
      setPendingDownload(false)
      const url = jobsApi.downloadUrl(job.id)
      const a = document.createElement('a')
      a.href = url
      a.download = ''
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    }
  }, [pendingDownload, job?.status, job?.output_path, job?.id])

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
          {job?.title || (
            resolvedPluginId === 'music_video' ? 'Music Video Editor' :
            resolvedPluginId === 'prompt_to_video' ? 'Prompt to Video Editor' :
            resolvedPluginId === 'script_to_video' ? 'Script to Video Editor' :
            'Scene Editor'
          )}
        </h1>
      </div>

      {/* Workflow Progress Bar */}
      <div className="bg-card rounded-lg border p-4 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Workflow Progress</h2>
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-primary">
              Current Stage: {getCurrentStageLabel()}
            </span>
            {isOperationInProgress && (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => cancelMutation.mutate()}
                disabled={cancelMutation.isPending}
              >
                <XCircle className="h-4 w-4 mr-2" />
                {cancelMutation.isPending ? 'Cancelling…' : 'Cancel'}
              </Button>
            )}
          </div>
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
        <div className={cn("lg:col-span-3 space-y-6", (isRegenerating || isOperationInProgress) && "pointer-events-none opacity-50")}>
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

              {/* Model Switcher */}
              <ModelSwitcher
                job={job}
                onModelsChanged={() => {
                  queryClient.invalidateQueries({ queryKey: ['job', job?.id] })
                  refetchScenes()
                }}
              />
              {/* Scene list */}
              <div className="bg-card rounded-lg border p-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold">Scenes ({scenes?.length || 0})</h3>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => createSceneMutation.mutate()}
                    disabled={createSceneMutation.isPending || isOperationInProgress}
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
                              {(scene.status === 'failed' || scene.status === 'error') && scene.error_message && (
                                <span className="flex items-center gap-1 text-xs text-red-500 cursor-help" title={scene.error_message}>
                                  <AlertCircle className="h-3 w-3" />
                                  {scene.error_message.substring(0, 80)}{scene.error_message.length > 80 ? '…' : ''}
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
                            {!scene.reference_image_path && canGenerateImages() && !isOperationInProgress && (
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
                            {scene.reference_image_path && canGenerateVideos() && (
                              // Video button always available when image exists
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => generateVideoMutation.mutate(scene.id)}
                                disabled={generateVideoMutation.isPending}
                                title={scene.generated_video_path ? 'Regenerate video for this scene' : 'Generate video for this scene'}
                              >
                                <Video className="h-4 w-4" />
                              </Button>
                            )}
                            {!isOperationInProgress && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setEditingScene(scene)}
                                title="Edit scene"
                              >
                                <Pencil className="h-4 w-4" />
                              </Button>
                            )}
                            {!isOperationInProgress && (
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
                            )}
                          </div>
                        </div>

                        {/* Status indicators */}
                        <div className="flex items-center gap-4 mt-2">
                          <div className="flex items-center gap-2">
                            {scene.reference_image_path ? (
                              <span className="flex items-center gap-1 text-xs text-green-600">
                                <CheckCircle className="h-3 w-3" /> Image Ready
                              </span>
                            ) : scene.status === 'generating_image' || scene.status === 'generating' ? (
                              <span className="flex items-center gap-1 text-xs text-yellow-600">
                                <Clock className="h-3 w-3" /> Generating Image…
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
                            ) : scene.status === 'generating_video' || scene.status === 'generating' ? (
                              <span className="flex items-center gap-1 text-xs text-yellow-600">
                                <Clock className="h-3 w-3" /> Generating Video…
                              </span>
                            ) : (
                              <span className="text-xs text-muted-foreground">No video</span>
                            )}
                          </div>
                        </div>

                        {/* Media preview — show image AND video side by side */}
                        <div className="mt-3 flex gap-3">
                          {/* Image thumbnail — always show if available */}
                          {scene.reference_image_path && (
                            <div className="relative">
                              <img
                                src={`/api/uploads/stream/${scene.reference_image_path}`}
                                alt={`Scene ${index + 1} image`}
                                className="h-24 object-cover rounded-lg border"
                              />
                              <span className="absolute bottom-1 left-1 bg-black/70 text-white text-[10px] px-1.5 py-0.5 rounded font-medium">
                                IMAGE
                              </span>
                            </div>
                          )}
                          {/* Video player — shown next to image */}
                          {scene.generated_video_path && (
                            <div className="relative">
                              <video
                                src={`/api/uploads/stream/${scene.generated_video_path}`}
                                className="h-24 object-cover rounded-lg border"
                                controls
                                muted
                                preload="metadata"
                                onError={(e) => {
                                  const vid = e.currentTarget
                                  if (!vid.dataset.retried) {
                                    vid.dataset.retried = '1'
                                    vid.src = `/api/uploads/stream/${scene.generated_video_path}`
                                  }
                                }}
                              />
                              <span className="absolute bottom-1 left-1 bg-primary text-primary-foreground text-[10px] px-1.5 py-0.5 rounded font-medium">
                                VIDEO
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between">
                <Button
                  variant="outline"
                  onClick={() => {
                    if (confirm('This will re-plan all scenes and regenerate all images and videos. Continue?')) {
                      regenerateAllMutation.mutate()
                    }
                  }}
                  disabled={regenerateAllMutation.isPending || isRegenerating || isOperationInProgress}
                >
                  <RefreshCw className={cn("h-4 w-4 mr-2", (regenerateAllMutation.isPending || isRegenerating) && "animate-spin")} />
                  {isRegenerating ? 'Regenerating...' : 'Regenerate All'}
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
        <div className={cn("space-y-4", (isRegenerating || isOperationInProgress) && "pointer-events-none opacity-50")}>
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
            setPendingDownload(true)
            queryClient.invalidateQueries({ queryKey: ['job', jobId] })
          }}
        />
      )}

      {/* Regeneration overlay */}
      {(isRegenerating || regenerateAllMutation.isPending) && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-4 p-8 bg-card rounded-2xl border shadow-2xl">
            <Loader2 className="h-12 w-12 text-primary animate-spin" />
            <div className="text-center">
              <h3 className="text-lg font-semibold">Regenerating All Scenes</h3>
              <p className="text-sm text-muted-foreground mt-1">
                {regenerateAllMutation.isPending
                  ? 'Re-planning scenes...'
                  : job?.stage === 'generating_images'
                    ? `Generating images (0/${scenes?.length || 0})...`
                    : job?.stage === 'generating_videos'
                      ? `Generating videos (0/${scenes?.length || 0})...`
                      : job?.stage === 'images_ready'
                        ? 'Images done, starting videos...'
                        : job?.stage === 'rendering'
                          ? 'Rendering final video...'
                          : 'Processing...'}
              </p>
            </div>
            <div className="w-48 h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-primary rounded-full transition-all duration-500"
                style={{
                  width:
                    job?.stage === 'generating_images' ? '30%'
                    : job?.stage === 'images_ready' ? '50%'
                    : job?.stage === 'generating_videos' ? '70%'
                    : job?.stage === 'rendering' ? '90%'
                    : '10%',
                }}
              />
            </div>
          </div>
        </div>
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


// ── Model Switcher ───────────────────────────────────────────────

function ModelSwitcher({ job, onModelsChanged }: { job?: { id: string; input_data?: Record<string, unknown> | null } | null; onModelsChanged: () => void }) {
  const [showModels, setShowModels] = useState(false)
  const [saving, setSaving] = useState(false)

  const { data: availableModels } = useQuery({
    queryKey: ['availableModels'],
    queryFn: () => modelsApi.getAvailableModels(),
  })

  const currentVideo = (job?.input_data as Record<string,unknown> | null)?.video_model as string || ''
  const currentImage = (job?.input_data as Record<string,unknown> | null)?.image_model as string || ''

  const handleModelChange = async (key: string, value: string) => {
    if (!job?.id) return
    setSaving(true)
    try {
      const inputData = { ...(job.input_data || {}), [key]: value }
      await jobsApi.patch(job.id, { input_data: inputData })
      onModelsChanged()
    } catch (e) {
      console.error('Failed to update model:', e)
    } finally {
      setSaving(false)
    }
  }

  const renderSelect = (label: string, models: any[] | undefined, selected: string, key: string) => (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium w-16">{label}</span>
      <select
        className="flex-1 h-8 rounded border px-2 text-xs bg-background"
        value={selected}
        onChange={(e) => handleModelChange(key, e.target.value)}
        disabled={saving}
      >
        {models?.map((m: any) => (
          <option key={m.id} value={m.id}>{m.name} ({m.provider === 'local' ? 'Local' : 'Cloud'})</option>
        )) || <option value="">Loading...</option>}
      </select>
    </div>
  )

  return (
    <div className="bg-card rounded-lg border">
      <button
        onClick={() => setShowModels(!showModels)}
        className="w-full flex items-center justify-between px-4 py-2 text-sm font-medium hover:bg-muted/50 rounded-t-lg"
      >
        <span>Model Settings</span>
        <span className="text-xs text-muted-foreground">
          Video: {currentVideo?.split(':').pop()?.split('/')[0] || 'default'} | Image: {currentImage?.split(':').pop()?.split('/')[0] || 'default'}
        </span>
      </button>
      {showModels && (
        <div className="px-4 py-3 border-t space-y-2">
          {renderSelect('Video', availableModels?.video_models, currentVideo, 'video_model')}
          {renderSelect('Image', availableModels?.image_models, currentImage, 'image_model')}
          <p className="text-xs text-muted-foreground pt-1">
            {saving ? 'Saving...' : 'Changes apply to the next generation run for all scenes.'}
          </p>
        </div>
      )}
    </div>
  )
}
