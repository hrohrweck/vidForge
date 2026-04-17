import axios from 'axios'
import { useAuthStore } from '../stores/auth'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout()
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
  provider_type: 'comfyui_direct' | 'runpod' | 'poe'
  config: Record<string, unknown>
  is_active: boolean
  daily_budget_limit: number | null
  current_daily_spend: number
  priority: number
  created_at: string
}

export interface ProviderCreateRequest {
  name: string
  provider_type: 'comfyui_direct' | 'runpod' | 'poe'
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
  type: 'comfyui_direct' | 'runpod' | 'poe'
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
}

export interface CreateJobRequest {
  template_id?: string
  input_data?: Record<string, unknown>
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
  delete: (id: string) => api.delete(`/jobs/${id}`),
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
}

export const usersApi = {
  getSettings: () => api.get('/users/settings'),
  updateSettings: (settings: Record<string, unknown>) => api.put('/users/settings', settings),
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
  duration: number
  language: string
}

export const scenesApi = {
  extractLyrics: async (jobId: string, request: LyricsExtractRequest) => {
    const response = await api.post<{ lyrics: LyricsData }>(
      `/scenes/${jobId}/lyrics/extract`,
      request
    )
    return response.data
  },

  setManualLyrics: async (jobId: string, request: ManualLyricsRequest) => {
    const response = await api.post<{ lyrics: LyricsData }>(
      `/scenes/${jobId}/lyrics/manual`,
      request
    )
    return response.data
  },

  planScenes: async (jobId: string, request: ScenePlanRequest) => {
    const response = await api.post<{ scenes: VideoScene[] }>(
      `/scenes/${jobId}/scenes/plan`,
      request
    )
    return response.data
  },

  listScenes: async (jobId: string) => {
    const response = await api.get<VideoScene[]>(`/scenes/${jobId}/scenes`)
    return response.data
  },

  getScene: async (jobId: string, sceneId: string) => {
    const response = await api.get<VideoScene>(
      `/scenes/${jobId}/scenes/${sceneId}`
    )
    return response.data
  },

  updateScene: async (jobId: string, sceneId: string, data: SceneUpdate) => {
    const response = await api.patch<VideoScene>(
      `/scenes/${jobId}/scenes/${sceneId}`,
      data
    )
    return response.data
  },

  reorderScenes: async (jobId: string, sceneIds: string[]) => {
    const response = await api.post<{ scenes: VideoScene[] }>(
      `/scenes/${jobId}/scenes/reorder`,
      { scene_ids: sceneIds }
    )
    return response.data
  },

  generateImage: async (jobId: string, sceneId: string) => {
    const response = await api.post<{ status: string; scene_id: string; media_type: string }>(
      `/scenes/${jobId}/scenes/generate-image/${sceneId}`
    )
    return response.data
  },

  generateVideo: async (jobId: string, sceneId: string) => {
    const response = await api.post<{ status: string; scene_id: string; media_type: string }>(
      `/scenes/${jobId}/scenes/generate-video/${sceneId}`
    )
    return response.data
  },

  generateAllImages: async (jobId: string, request?: SceneGenerateRequest) => {
    const response = await api.post<{ status: string; job_id: string; stage: string }>(
      `/scenes/${jobId}/scenes/generate-all-images`,
      request || {}
    )
    return response.data
  },

  generateAllVideos: async (jobId: string, request?: SceneGenerateRequest) => {
    const response = await api.post<{ status: string; job_id: string; stage: string }>(
      `/scenes/${jobId}/scenes/generate-all-videos`,
      request || {}
    )
    return response.data
  },

  export: async (jobId: string, request: ExportRequest) => {
    const response = await api.post<{ status: string; job_id: string; stage: string }>(
      `/scenes/${jobId}/export`,
      request
    )
    return response.data
  },

  getExportOptions: async (jobId: string) => {
    const response = await api.get<ExportOptions>(`/scenes/${jobId}/export-options`)
    return response.data
  },

  getLyrics: async (jobId: string) => {
    const response = await api.get<{ lyrics: LyricsData | null }>(
      `/scenes/${jobId}/lyrics`
    )
    return response.data
  },

  getStage: async (jobId: string) => {
    const response = await api.get<StageUpdate>(`/scenes/${jobId}/stage`)
    return response.data
  },
}
