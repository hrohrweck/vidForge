import api from './client'

export type AvatarGender = 'Male' | 'Female' | 'Non-binary' | 'Other'

export type ConsistencyStrategy = 'ip_adapter' | 'face_swap' | 'lora' | 'prompt_only'

export interface AvatarImage {
  id: string
  storagePath: string
  isPrimary: boolean
  sortOrder: number
  width?: number
  height?: number
  thumbnailUrl?: string
}

export interface Avatar {
  id: string
  userId: string
  name: string
  gender: AvatarGender
  bio?: string
  consistencyStrategy: ConsistencyStrategy
  primaryImageId?: string
  images: AvatarImage[]
  jobCount: number
  loraTrainingStatus: 'not_trained' | 'training' | 'trained' | 'failed'
  createdAt: string
  updatedAt: string
}

export interface AvatarListResponse {
  avatars: Avatar[]
  total: number
}

export interface CreateAvatarRequest {
  name: string
  gender: AvatarGender
  bio?: string
  consistencyStrategy?: ConsistencyStrategy
}

export interface UpdateAvatarRequest {
  name?: string
  gender?: AvatarGender
  bio?: string
  consistencyStrategy?: ConsistencyStrategy
  primaryImageId?: string
}

export interface JobAvatarAssignment {
  avatarId: string
  role?: string
  consistencyStrategyOverride?: ConsistencyStrategy
}

async function list(): Promise<AvatarListResponse> {
  const response = await api.get<AvatarListResponse>('/avatars')
  return response.data
}

async function get(id: string): Promise<Avatar> {
  const response = await api.get<Avatar>(`/avatars/${id}`)
  return response.data
}

async function create(data: CreateAvatarRequest): Promise<Avatar> {
  const response = await api.post<Avatar>('/avatars', data)
  return response.data
}

async function update(id: string, data: UpdateAvatarRequest): Promise<Avatar> {
  const response = await api.put<Avatar>(`/avatars/${id}`, data)
  return response.data
}

async function remove(id: string): Promise<void> {
  await api.delete(`/avatars/${id}`)
}

async function uploadImage(avatarId: string, file: File): Promise<AvatarImage> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await api.post<AvatarImage>(`/avatars/${avatarId}/images`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data
}

async function setPrimaryImage(avatarId: string, imageId: string): Promise<Avatar> {
  const response = await api.put<Avatar>(`/avatars/${avatarId}/images/${imageId}/primary`)
  return response.data
}

async function deleteImage(avatarId: string, imageId: string): Promise<void> {
  await api.delete(`/avatars/${avatarId}/images/${imageId}`)
}

async function generatePoses(avatarId: string): Promise<void> {
  await api.post(`/avatars/${avatarId}/generate-poses`)
}

async function trainLora(avatarId: string): Promise<void> {
  await api.post(`/avatars/${avatarId}/train-lora`)
}

export const avatarsApi = {
  list,
  get,
  create,
  update,
  delete: remove,
  uploadImage,
  setPrimaryImage,
  deleteImage,
  generatePoses,
  trainLora,
}
