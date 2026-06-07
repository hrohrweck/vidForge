import api from './client'

export interface ObjectRefImage {
  id: string
  storage_path: string
  is_primary: boolean
  sort_order: number
  width?: number
  height?: number
}

export interface ObjectRef {
  id: string
  user_id: string
  name: string
  description?: string
  visual_properties?: Record<string, unknown>
  category?: string
  images: ObjectRefImage[]
  job_count: number
  created_at: string
  updated_at: string
}

export interface ObjectRefListResponse {
  objects: ObjectRef[]
  total: number
}

export const objectsApi = {
  list: async (params?: { skip?: number; limit?: number }) => {
    const response = await api.get<ObjectRefListResponse>('/objects', { params })
    return response.data
  },

  get: async (id: string) => {
    const response = await api.get<ObjectRef>(`/objects/${id}`)
    return response.data
  },

  delete: async (id: string) => {
    await api.delete(`/objects/${id}`)
  },
}
