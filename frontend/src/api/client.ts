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
  provider_preference: 'auto' | 'comfyui_direct' | 'runpod'
  model_preference: string | null
  estimated_cost: number | null
  actual_cost: number | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface CreateJobRequest {
  template_id?: string
  input_data?: Record<string, unknown>
  auto_start?: boolean
  provider_preference?: 'auto' | 'comfyui_direct' | 'runpod'
  model_preference?: string
}

export interface BatchJobRequest {
  template_id: string
  jobs: Record<string, unknown>[]
  auto_start?: boolean
  provider_preference?: 'auto' | 'comfyui_direct' | 'runpod'
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
  provider: 'wan' | 'ltx'
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
    providerPreference: 'auto' | 'comfyui_direct' | 'runpod' = 'auto',
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
