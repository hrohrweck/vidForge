import api from './client'

export interface ObjectRefImage {
  id: string
  storagePath: string
  isPrimary: boolean
  sortOrder: number
  width?: number
  height?: number
}

export interface ObjectRefImageUploadResponse {
  image: ObjectRefImage
  object: ObjectRef
}

export interface ObjectRef {
  id: string
  userId: string
  name: string
  description?: string
  visualProperties?: Record<string, unknown>
  category?: string
  images: ObjectRefImage[]
  jobCount: number
  createdAt: string
  updatedAt: string
}

export interface ObjectRefListResponse {
  objects: ObjectRef[]
  total: number
}

export interface CreateObjectRefRequest {
  name: string
  description?: string
  category?: string
  visualProperties?: Record<string, unknown>
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

  create: async (data: CreateObjectRefRequest): Promise<ObjectRef> => {
    const response = await api.post<ObjectRef>('/objects', data)
    return response.data
  },

  uploadImage: async (objectId: string, file: File): Promise<ObjectRefImageUploadResponse> => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await api.post<ObjectRefImageUploadResponse>(
      `/objects/${objectId}/images`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    return response.data
  },
}
