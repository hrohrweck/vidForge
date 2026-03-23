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

export interface User {
  id: string
  email: string
  is_active: boolean
}

export interface Job {
  id: string
  status: string
  progress: number
  input_data: Record<string, unknown> | null
  output_path: string | null
  preview_path: string | null
  thumbnail_path: string | null
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface CreateJobRequest {
  template_id?: string
  input_data?: Record<string, unknown>
}

export interface BatchJobRequest {
  template_id: string
  jobs: Record<string, unknown>[]
  auto_start?: boolean
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
  createFromCsv: async (templateId: string, file: File, autoStart: boolean = true) => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await api.post<BatchJobResponse>(`/jobs/batch/csv?template_id=${templateId}&auto_start=${autoStart}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
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

export const usersApi = {
  getSettings: () => api.get('/users/settings'),
  updateSettings: (settings: Record<string, unknown>) => api.put('/users/settings', settings),
}
