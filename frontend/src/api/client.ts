import axios from 'axios'
import { useAuthStore } from '../stores/auth'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
})

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let isRefreshing = false
let failedQueue: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = []

const processQueue = (token: string | null, error: unknown = null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error)
    else resolve(token!)
  })
  failedQueue = []
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`
          return api(originalRequest)
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        const response = await api.post<TokenResponse>('/auth/refresh')
        const newToken = response.data.access_token
        useAuthStore.getState().setToken(newToken)
        processQueue(newToken)
        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return api(originalRequest)
      } catch (refreshError) {
        processQueue(null, refreshError)
        useAuthStore.getState().logout()
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(error)
  }
)

export default api

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface Group {
  id: string
  name: string
  description?: string
  permissions?: Permission[]
  users_count?: number
}

export interface Permission {
  id: string
  name: string
  description?: string
  category: string
}

export interface User {
  id: string
  email: string
  is_active: boolean
  is_superuser: boolean
  groups: Group[]
  permissions: string[]
}

export interface UserDetail {
  id: string
  email: string
  is_active: boolean
  is_superuser: boolean
  groups: Group[]
  permissions: string[]
  jobs_count: number
  created_at: string
}

export interface DeletePreview {
  user_id: string
  email: string
  items_to_delete: Record<string, number>
  total_items: number
  warning: string
}

export interface UserUpdateRequest {
  is_active?: boolean
  is_superuser?: boolean
  group_ids?: string[]
}

export interface Provider {
  id: string
  name: string
  provider_type: 'comfyui_direct' | 'runpod' | 'poe' | 'atlascloud'
  config: Record<string, unknown>
  is_active: boolean
  daily_budget_limit: number | null
  current_daily_spend: number
  priority: number
  created_at: string
}

export interface ProviderCreateRequest {
  name: string
  provider_type: 'comfyui_direct' | 'runpod' | 'poe' | 'atlascloud'
  config: Record<string, unknown>
  daily_budget_limit?: number | null
  priority?: number
}

export interface ProviderUpdateRequest {
  name?: string
  config?: Record<string, unknown>
  daily_budget_limit?: number | null
  priority?: number
  is_active?: boolean
}

export interface ProviderStatus {
  id: string
  name: string
  type: 'comfyui_direct' | 'runpod' | 'poe' | 'atlascloud'
  is_available: boolean
  estimated_wait_seconds: number
  message: string
  workers: {
    total: number
    online: number
    busy: number
    offline: number
  } | null
  daily_budget_limit: number | null
  current_daily_spend: number
}

export interface PoeModel {
  id: string
  provider_id: string
  name: string
  model_id: string
  modality: 'video' | 'image' | 'text'
  is_active: boolean
  created_at: string
}

export interface PoeModelCreate {
  name: string
  model_id: string
  modality: 'video' | 'image' | 'text'
}

export interface PoeModelUpdate {
  name?: string
  model_id?: string
  modality?: 'video' | 'image' | 'text'
  is_active?: boolean
}

export interface GroupCreateRequest {
  name: string
  description?: string
  permission_ids?: string[]
}

export interface GroupUpdateRequest {
  name?: string
  description?: string
  permission_ids?: string[]
}

export interface Job {
  id: string
  title: string
  status: string
  stage: string
  progress: number
  input_data: Record<string, unknown> | null
  output_path: string | null
  preview_path: string | null
  thumbnail_path: string | null
  error_message: string | null
  provider_id: string | null
  provider_type: string | null
  provider_preference: string
  model_preference: string | null
  estimated_cost: number | null
  actual_cost: number | null
  workflow_type: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  template_id?: string
  cost?: number | null
}

export interface CreateJobRequest {
  title?: string
  template_id?: string
  project_id?: string
  input_data?: Record<string, unknown> & {
    avatars?: Array<{
      avatarId: string
      role?: string
      consistencyStrategyOverride?: string
    }>
  }
  auto_start?: boolean
  provider_preference?: string
  model_preference?: string
}

export interface BatchJobRequest {
  template_id: string
  jobs: Record<string, unknown>[]
  auto_start?: boolean
  provider_preference?: string
  model_preference?: string
}

export interface BatchJobResponse {
  created_count: number
  job_ids: string[]
}

export interface Template {
  id: string
  name: string
  description: string | null
  config: Record<string, unknown>
  is_builtin: boolean
  created_at: string
}

export interface CreateTemplateRequest {
  name: string
  description?: string
  config: Record<string, unknown>
}

export interface Style {
  id: string
  name: string
  category: string | null
  params: Record<string, unknown>
  created_at: string
}

export interface VideoModel {
  id: string
  name: string
  display_name: string
  provider: 'wan' | 'ltx' | 'poe'
  modality: 'video' | 'image'
  capabilities: string[]
  max_duration: number
  max_resolution: [number, number]
  default_steps: number
  distilled: boolean
  description: string
}

export const authApi = {
  login: (data: LoginRequest) => api.post<TokenResponse>('/auth/login', data),
  register: (data: RegisterRequest) => api.post<User>('/auth/register', data),
  getMe: () => api.get<User>('/auth/me'),
  refreshToken: () => api.post<TokenResponse>('/auth/refresh'),
}

export const jobsApi = {
  list: async (params?: { status?: string; limit?: number; offset?: number }) => {
    const response = await api.get<Job[]>('/jobs', { params })
    return response.data
  },
  get: async (id: string) => {
    const response = await api.get<Job>(`/jobs/${id}`)
    return response.data
  },
  create: async (data: CreateJobRequest) => {
    const response = await api.post<Job>('/jobs', data)
    return response.data
  },
  createBatch: async (data: BatchJobRequest) => {
    const response = await api.post<BatchJobResponse>('/jobs/batch', data)
    return response.data
  },
  createFromCsv: async (
    templateId: string,
    file: File,
    autoStart: boolean = true,
    providerPreference: string = 'auto',
    modelPreference?: string
  ) => {
    const formData = new FormData()
    formData.append('file', file)
    let url = `/jobs/batch/csv?template_id=${templateId}&auto_start=${autoStart}&provider_preference=${providerPreference}`
    if (modelPreference) {
      url += `&model_preference=${modelPreference}`
    }
    const response = await api.post<BatchJobResponse>(
      url,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    return response.data
  },
  start: async (id: string) => {
    const response = await api.post<{ status: string; job_id: string }>(`/jobs/${id}/start`)
    return response.data
  },
  retry: async (id: string) => {
    const response = await api.post<Job>(`/jobs/${id}/retry`)
    return response.data
  },
  patch: async (id: string, data: { input_data?: Record<string, unknown> }) => {
    const response = await api.patch<Job>(`/jobs/${id}`, data)
    return response.data
  },
  delete: (id: string) => api.delete(`/jobs/${id}`),

  downloadUrl: (id: string) => {
    // Returns a URL that triggers a browser download with Content-Disposition
    const token = localStorage.getItem('token')
    return `/api/jobs/${id}/download?token=${token}`
  },
}

export const templatesApi = {
  list: () => api.get<Template[]>('/templates'),
  get: (id: string) => api.get<Template>(`/templates/${id}`),
  create: (data: CreateTemplateRequest) => api.post<Template>('/templates', data),
  update: (id: string, data: CreateTemplateRequest) =>
    api.put<Template>(`/templates/${id}`, data),
  delete: (id: string) => api.delete(`/templates/${id}`),
}

export const stylesApi = {
  list: (category?: string) =>
    api.get<Style[]>('/styles', { params: { category } }),
  get: (id: string) => api.get<Style>(`/styles/${id}`),
}

export const storageApi = {
  getConfig: () => api.get('/storage/config'),
  listFiles: (prefix: string = '') => api.get('/storage/files', { params: { prefix } }),
  deleteFile: (path: string) => api.delete(`/storage/files/${path}`),
}

export const providersApi = {
  list: async () => {
    const response = await api.get<Provider[]>('/providers')
    return response.data
  },
  create: async (data: ProviderCreateRequest) => {
    const response = await api.post<Provider>('/providers', data)
    return response.data
  },
  update: async (id: string, data: ProviderUpdateRequest) => {
    const response = await api.patch<Provider>(`/providers/${id}`, data)
    return response.data
  },
  delete: async (id: string) => {
    await api.delete(`/providers/${id}`)
  },
  getStatus: async (id: string) => {
    const response = await api.get<ProviderStatus>(`/providers/${id}/status`)
    return response.data
  },
  getStatuses: async () => {
    const response = await api.get<ProviderStatus[]>('/providers/status')
    return response.data
  },
  resetSpend: async (id: string) => {
    const response = await api.post<{ status: string }>(`/providers/${id}/reset-spend`)
    return response.data
  },
  setBudget: async (id: string, daily_budget_limit: number | null) => {
    const response = await api.patch<{ daily_budget_limit: number | null }>(
      `/providers/${id}/budget`,
      { daily_budget_limit }
    )
    return response.data
  },
  listPoeModels: async (providerId: string) => {
    const response = await api.get<PoeModel[]>(`/providers/${providerId}/poe-models`)
    return response.data
  },
  createPoeModel: async (providerId: string, data: PoeModelCreate) => {
    const response = await api.post<PoeModel>(`/providers/${providerId}/poe-models`, data)
    return response.data
  },
  updatePoeModel: async (providerId: string, modelId: string, data: PoeModelUpdate) => {
    const response = await api.patch<PoeModel>(`/providers/${providerId}/poe-models/${modelId}`, data)
    return response.data
  },
  deletePoeModel: async (providerId: string, modelId: string) => {
    await api.delete(`/providers/${providerId}/poe-models/${modelId}`)
  },

  // AtlasCloud Models
  listAtlasCloudModels: async (providerId: string) => {
    const response = await api.get<PoeModel[]>(`/providers/${providerId}/atlascloud-models`)
    return response.data
  },
  createAtlasCloudModel: async (providerId: string, data: PoeModelCreate) => {
    const response = await api.post<PoeModel>(`/providers/${providerId}/atlascloud-models`, data)
    return response.data
  },
  updateAtlasCloudModel: async (providerId: string, modelId: string, data: PoeModelUpdate) => {
    const response = await api.patch<PoeModel>(`/providers/${providerId}/atlascloud-models/${modelId}`, data)
    return response.data
  },
  deleteAtlasCloudModel: async (providerId: string, modelId: string) => {
    await api.delete(`/providers/${providerId}/atlascloud-models/${modelId}`)
  },
}

export const modelsApi = {
  list: async () => {
    const response = await api.get<VideoModel[]>('/models')
    return response.data
  },
  get: async (id: string) => {
    const response = await api.get<VideoModel>(`/models/${id}`)
    return response.data
  },
  getAvailableModels: async () => {
    const response = await api.get<{ image_models: ModelConfig[]; video_models: ModelConfig[]; text_models: ModelConfig[] }>('/models/available')
    return response.data
  },
  getModelPreferences: async () => {
    const response = await api.get<ModelPreferences>('/models/preferences')
    return response.data
  },
  updateModelPreferences: async (prefs: ModelPreferences) => {
    const response = await api.put<ModelPreferences>('/models/preferences', prefs)
    return response.data
  },
}

export const usersApi = {
  getSettings: () => api.get('/users/settings'),
  updateSettings: (settings: Record<string, unknown>) => api.put('/users/settings', settings),
}

export const healthApi = {
  getModels: async () => {
    const response = await api.get<{ models: Record<string, string>; error?: string }>(
      '/health/models'
    )
    return response.data
  },
}


// ─── Admin Notification Types ────────────────────────────────
export type ErrorSeverity = 'info' | 'warning' | 'error' | 'critical'
export type ErrorOrigin =
  | 'media_generation'
  | 'video_generation'
  | 'audio_generation'
  | 'llm'
  | 'storage'
  | 'upload'
  | 'system'

export interface AdminErrorEvent {
  id: string
  userId: string | null
  severity: ErrorSeverity
  origin: ErrorOrigin
  message: string
  details: Record<string, unknown> | null
  sourceId: string | null
  sourceType: string | null
  createdAt: string
  readAt: string | null
}

export interface AdminErrorEventListResponse {
  items: AdminErrorEvent[]
  total: number
  unreadCount: number
}

export interface AdminNotificationListParams {
  severity?: ErrorSeverity[]
  origin?: ErrorOrigin[]
  userId?: string
  unreadOnly?: boolean
  limit?: number
  offset?: number
}

export const adminApi = {
  getDashboard: async () => {
    const response = await api.get('/admin/dashboard')
    return response.data
  },

  getUsers: async () => {
    const response = await api.get<UserDetail[]>('/admin/users')
    return response.data
  },

  getUser: async (id: string) => {
    const response = await api.get<UserDetail>(`/admin/users/${id}`)
    return response.data
  },

  previewUserDeletion: async (id: string) => {
    const response = await api.get<DeletePreview>(`/admin/users/${id}/preview-delete`)
    return response.data
  },

  updateUser: async (id: string, data: UserUpdateRequest) => {
    const response = await api.patch<UserDetail>(`/admin/users/${id}`, data)
    return response.data
  },

  deleteUser: async (id: string) => {
    await api.delete(`/admin/users/${id}`)
  },

  getGroups: async () => {
    const response = await api.get<Group[]>('/admin/groups')
    return response.data
  },

  createGroup: async (data: GroupCreateRequest) => {
    const response = await api.post<Group>('/admin/groups', data)
    return response.data
  },

  updateGroup: async (id: string, data: GroupUpdateRequest) => {
    const response = await api.patch<Group>(`/admin/groups/${id}`, data)
    return response.data
  },

  deleteGroup: async (id: string) => {
    await api.delete(`/admin/groups/${id}`)
  },

  getPermissions: async () => {
    const response = await api.get<Permission[]>('/admin/permissions')
    return response.data
  },

  // ─── Admin Notifications ──────────────────────────────────
  getNotifications: async (params?: AdminNotificationListParams) => {
    const queryParams: Record<string, string> = {}
    if (params?.severity?.length) queryParams['severity'] = params.severity.join(',')
    if (params?.origin?.length) queryParams['origin'] = params.origin.join(',')
    if (params?.userId) queryParams['userId'] = params.userId
    if (params?.unreadOnly) queryParams['unreadOnly'] = 'true'
    if (params?.limit != null) queryParams['limit'] = String(params.limit)
    if (params?.offset != null) queryParams['offset'] = String(params.offset)
    const response = await api.get<AdminErrorEventListResponse>('/admin/notifications', {
      params: queryParams,
      paramsSerializer: (p) => {
        const parts: string[] = []
        for (const [key, value] of Object.entries(p)) {
          if (Array.isArray(value)) {
            value.forEach((v) => parts.push(`${key}=${encodeURIComponent(v)}`))
          } else if (value != null) {
            parts.push(`${key}=${encodeURIComponent(String(value))}`)
          }
        }
        return parts.join('&')
      },
    })
    return response.data
  },

  getNotification: async (eventId: string) => {
    const response = await api.get<AdminErrorEvent>(`/admin/notifications/${eventId}`)
    return response.data
  },

  deleteNotification: async (eventId: string) => {
    await api.delete(`/admin/notifications/${eventId}`)
  },
}

export interface VideoScene {
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
  image_provider_id: string | null
  video_provider_id: string | null
  image_prompt_enhanced: string | null
  duration: number | null
  model_used: string | null
  error_message: string | null
  created_at: string
}

export interface LyricsExtractRequest {
  audio_file_path: string
}

export interface ManualLyricsRequest {
  lyrics_text: string
  duration: number
}

export interface ScenePlanRequest {
  lyrics_data: Record<string, unknown>
  duration: number
  style: string
}

export interface SceneUpdate {
  start_time?: number
  end_time?: number
  lyrics_segment?: string
  visual_description?: string
  image_prompt?: string
  mood?: string
  camera_movement?: string
  reference_image_path?: string
}

export interface SceneGenerateRequest {
  image_provider_id?: string
  video_provider_id?: string
}

export interface ExportRequest {
  audio_file?: string
  background_music?: string
  audio_volume?: number
  background_music_volume?: number
  transition_type?: string
}

export interface ExportOptions {
  job_id: string
  audio_file: string | null
  can_export: boolean
  completed_scenes: number
  total_scenes: number
  transition_types: string[]
  default_options: {
    audio_volume: number
    background_music_volume: number
    transition_type: string
  }
}

export interface StageUpdate {
  stage: string
  progress: number
  status: string
}

export interface LyricsData {
  lyrics: Array<{
    start: number
    end: number
    text: string
  }>
  lines?: Array<{
    start: number
    end: number
    text: string
  }>
  full_text?: string
  duration: number
  language?: string
}

export const scenesApi = {
  extractLyrics: async (jobId: string, request: LyricsExtractRequest) => {
    const response = await api.post<{ lyrics: LyricsData }>(
      `/jobs/${jobId}/lyrics/extract`,
      request
    )
    return response.data
  },

  getAudioMetadata: async (jobId: string) => {
    const response = await api.get<{ duration: number; path: string }>(
      `/jobs/${jobId}/audio-metadata`
    )
    return response.data
  },

  setManualLyrics: async (jobId: string, request: ManualLyricsRequest) => {
    const response = await api.post<{ lyrics: LyricsData }>(
      `/jobs/${jobId}/lyrics/manual`,
      request
    )
    return response.data
  },

  updateLyrics: async (jobId: string, request: { lyrics_text: string; duration: number; replan?: boolean; style?: string }) => {
    const response = await api.put<{ lyrics: LyricsData; scenes?: VideoScene[]; summary?: string }>(
      `/jobs/${jobId}/lyrics`,
      request
    )
    return response.data
  },

  planScenes: async (jobId: string, request: ScenePlanRequest) => {
    const response = await api.post<{ scenes: VideoScene[] }>(
      `/jobs/${jobId}/scenes/plan`,
      request
    )
    return response.data
  },

  listScenes: async (jobId: string) => {
    const response = await api.get<VideoScene[]>(`/jobs/${jobId}/scenes`)
    return response.data
  },

  getScene: async (jobId: string, sceneId: string) => {
    const response = await api.get<VideoScene>(
      `/jobs/${jobId}/scenes/${sceneId}`
    )
    return response.data
  },

  updateScene: async (jobId: string, sceneId: string, data: SceneUpdate) => {
    const response = await api.patch<VideoScene>(
      `/jobs/${jobId}/scenes/${sceneId}`,
      data
    )
    return response.data
  },

  reorderScenes: async (jobId: string, sceneIds: string[]) => {
    const response = await api.post<{ scenes: VideoScene[] }>(
      `/jobs/${jobId}/scenes/reorder`,
      { scene_ids: sceneIds }
    )
    return response.data
  },

  createScene: async (jobId: string) => {
    const response = await api.post<VideoScene>(`/jobs/${jobId}/scenes`)
    return response.data
  },

  deleteScene: async (jobId: string, sceneId: string) => {
    const response = await api.delete<{ status: string }>(`/jobs/${jobId}/scenes/${sceneId}`)
    return response.data
  },

  generateImage: async (jobId: string, sceneId: string) => {
    const response = await api.post<{ status: string; scene_id: string; media_type: string }>(
      `/jobs/${jobId}/scenes/generate-image/${sceneId}`
    )
    return response.data
  },

  generateVideo: async (jobId: string, sceneId: string) => {
    const response = await api.post<{ status: string; scene_id: string; media_type: string }>(
      `/jobs/${jobId}/scenes/generate-video/${sceneId}`
    )
    return response.data
  },

  generateAllImages: async (jobId: string, request?: SceneGenerateRequest) => {
    const response = await api.post<{ status: string; job_id: string; stage: string }>(
      `/jobs/${jobId}/scenes/generate-all-images`,
      request || {}
    )
    return response.data
  },

  regenerateAll: async (jobId: string) => {
    const response = await api.post<{
      status: string
      job_id: string
      scene_count: number
      stage: string
    }>(
      `/jobs/${jobId}/scenes/regenerate-all`
    )
    return response.data
  },

  generateAllVideos: async (jobId: string, request?: SceneGenerateRequest) => {
    const response = await api.post<{ status: string; job_id: string; stage: string }>(
      `/jobs/${jobId}/scenes/generate-all-videos`,
      request || {}
    )
    return response.data
  },

  export: async (jobId: string, request: ExportRequest) => {
    const response = await api.post<{ status: string; job_id: string; stage: string }>(
      `/jobs/${jobId}/export`,
      request
    )
    return response.data
  },

  getExportOptions: async (jobId: string) => {
    const response = await api.get<ExportOptions>(`/jobs/${jobId}/export-options`)
    return response.data
  },

  getLyrics: async (jobId: string) => {
    const response = await api.get<{ lyrics: LyricsData | null }>(
      `/jobs/${jobId}/lyrics`
    )
    return response.data
  },

  getStage: async (jobId: string) => {
    const response = await api.get<StageUpdate>(`/jobs/${jobId}/stage`)
    return response.data
  },

  updateStage: async (jobId: string, stage: string) => {
    const response = await api.patch<{ job_id: string; stage: string }>(
      `/jobs/${jobId}/stage`,
      { stage }
    )
    return response.data
  },

  cancel: async (jobId: string) => {
    const response = await api.post<{ status: string; job_id: string; stage: string }>(
      `/jobs/${jobId}/cancel`
    )
    return response.data
  },
}

export interface ModelConfig {
  id: string
  name: string
  display_name?: string
  description: string
  size_gb: number
  speed: string
  quality: string
  license: string
  provider: string
  provider_id?: string
  default: boolean
  capabilities?: Record<string, boolean>
  cost_config?: Record<string, unknown> | null
  resolutions?: string[] | null
  size_param_family?: string | null
  variants?: Record<string, { workflow: string; description: string }>
}

export interface ModelPreferences {
  image_model: string
  video_model: string
  text_model: string
  image_provider: string
  video_provider: string
  text_provider: string
  text_to_image_model: string
  image_to_image_model: string
  text_to_video_model: string
  image_to_video_model: string
  image_provider_id: string
  video_provider_id: string
  text_provider_id: string
  text_to_image_provider_id: string
  image_to_image_provider_id: string
  text_to_video_provider_id: string
  image_to_video_provider_id: string
}

// Chat API types and namespace

export interface MessagePart {
  type: 'text' | 'image' | 'audio' | 'script'
  content: string | Record<string, unknown>
}

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
}

export interface ToolResult {
  tool_call_id: string
  output?: string | null
  error?: string | null
}

export interface Conversation {
  id: string
  user_id: string
  title: string | null
  created_at: string
  updated_at: string
  last_message_at: string | null
}

export interface Message {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  parts: MessagePart[] | null
  tool_calls: ToolCall[] | null
  tool_call_id: string | null
  job_id: string | null
  created_at: string
  attachments?: Array<{url: string; type?: string; name?: string; kind?: string; mime_type?: string}>
}

export type ChatStreamEventType =
  | 'token'
  | 'tool_call_start'
  | 'tool_call_result'
  | 'error'
  | 'done'
  | 'usage'

export interface ChatStreamEvent {
  event: ChatStreamEventType
  data: Record<string, unknown>
}

export interface ChatStreamToolCallStart {
  event: 'tool_call_start'
  tool_call_id: string
  name: string
  arguments?: Record<string, unknown>
}

export interface ChatStreamToolResult {
  event: 'tool_call_result'
  tool_call_id: string
  output?: string
  error?: string
}

export interface ChatStreamError {
  event: 'error'
  error: string
}

export const chatApi = {
  listConversations: async () => {
    const response = await api.get<{ items: Conversation[] }>('/chat/conversations')
    return response.data.items
  },

  getConversation: async (id: string) => {
    const response = await api.get<Conversation>(`/chat/conversations/${id}`)
    return response.data
  },

  createConversation: async (title?: string, model_id?: string) => {
    const response = await api.post<Conversation>('/chat/conversations', { title, model_id })
    return response.data
  },

  renameConversation: async (id: string, title: string) => {
    const response = await api.patch<Conversation>(`/chat/conversations/${id}`, { title })
    return response.data
  },

  deleteConversation: async (id: string) => {
    await api.delete(`/chat/conversations/${id}`)
  },

  listMessages: async (conversationId: string) => {
    const response = await api.get<{ items: Message[] }>(`/chat/conversations/${conversationId}/messages`)
    return response.data.items
  },

  uploadAttachment: async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await api.post<{
      attachment_id: string
      kind: string
      mime_type: string
      size: number
      url: string
    }>('/chat/uploads', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },

  streamMessage: async function* (
    conversationId: string,
    content: string,
    modelId: string,
    attachments?: Array<{ kind: string; url: string; name?: string }>,
    signal?: AbortSignal
  ): AsyncGenerator<ChatStreamEvent, void, unknown> {
    const token = useAuthStore.getState().token
    const response = await fetch(`/api/chat/conversations/${conversationId}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        content,
        model_id: modelId,
        ...(attachments && attachments.length > 0 ? { attachments } : {}),
      }),
      signal,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Stream request failed' }))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }

    if (!response.body) {
      throw new Error('Response body is null')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const data = line.slice(6).trim()
            if (data && data !== '[DONE]') {
              try {
                const parsed = JSON.parse(data)
                yield { event: currentEvent, data: parsed } as ChatStreamEvent
              } catch {
              }
            }
            currentEvent = ''
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  },

  getTokenUsage: async () => {
    const response = await api.get<{ items: Array<{
      model_id: string
      prompt_tokens: number
      completion_tokens: number
      total_tokens: number
      estimated_cost: number | null
      message_count: number
    }> }>('/chat/token-usage')
    return response.data
  },
}

export interface TokenUsageBucket {
  timestamp: string
  model_id: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface CostBucket {
  timestamp: string
  model_id: string
  cost: number
}

export const dashboardApi = {
  getTokenUsageOverTime: async (from: string, to: string, groupBy: string) => {
    const response = await api.get<{ buckets: TokenUsageBucket[] }>(
      '/dashboard/token-usage',
      { params: { from, to, group_by: groupBy } }
    )
    return response.data
  },

  getCostOverTime: async (from: string, to: string, groupBy: string) => {
    const response = await api.get<{ buckets: CostBucket[] }>(
      '/dashboard/cost',
      { params: { from, to, group_by: groupBy } }
    )
    return response.data
  },
}

// MCP Admin API types and namespace

export interface MCPServer {
  id: string
  name: string
  description: string | null
  command: string
  args: string[] | null
  env_keys: string[] | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface MCPServerWithCredentials extends MCPServer {
  env: Record<string, string> | null
}

export interface MCPServerCreate {
  name: string
  description?: string
  command: string
  args?: string[]
  env?: Record<string, string>
}

export interface MCPServerUpdate {
  name?: string
  description?: string
  command?: string
  args?: string[]
  env?: Record<string, string>
  is_active?: boolean
}

export interface MCPTool {
  name: string
  description?: string
  input_schema?: Record<string, unknown>
}

export const mcpAdminApi = {
  listServers: async () => {
    const response = await api.get<MCPServer[]>('/mcp/servers')
    return response.data
  },

  createServer: async (data: MCPServerCreate) => {
    const response = await api.post<MCPServer>('/mcp/servers', data)
    return response.data
  },

  updateServer: async (id: string, data: MCPServerUpdate) => {
    const response = await api.patch<MCPServer>(`/mcp/servers/${id}`, data)
    return response.data
  },

  deleteServer: async (id: string) => {
    await api.delete(`/mcp/servers/${id}`)
  },

  listServerTools: async (id: string) => {
    const response = await api.get<MCPTool[]>(`/mcp/servers/${id}/tools`)
    return response.data
  },
}

// Notifications API
import type { ErrorEventListResponse, ErrorEventFilter } from './types/notifications'

export const notificationsApi = {
  list: async (filter?: ErrorEventFilter) => {
    const response = await api.get<ErrorEventListResponse>('/notifications', { params: filter })
    return response.data
  },

  markAsRead: async (id: string) => {
    await api.post(`/notifications/${id}/read`)
  },

  markAllRead: async () => {
    await api.post('/notifications/mark-all-read')
  },
}
