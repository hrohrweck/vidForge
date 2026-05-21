import api from './client'
import type {
  MediaFolder,
  FolderTreeItem,
  MediaAsset,
  AssetListQuery,
  AssetListResponse,
  AssetUpdatePayload,
  PreviewFrameRequest,
  MediaTag,
  BulkMoveRequest,
  BulkDeleteRequest,
  BulkTagRequest,
  UploadProgress,
} from './types/media'

export async function listFolders(parentId?: string): Promise<MediaFolder[]> {
  const params = parentId ? { parent_id: parentId } : {}
  const response = await api.get('/media/folders', { params })
  return response.data
}

export async function createFolder(payload: { name: string; parent_id?: string }): Promise<MediaFolder> {
  const response = await api.post('/media/folders', payload)
  return response.data
}

export async function updateFolder(id: string, payload: { name?: string; parent_id?: string }): Promise<MediaFolder> {
  const response = await api.patch(`/media/folders/${id}`, payload)
  return response.data
}

export async function deleteFolder(id: string): Promise<void> {
  await api.delete(`/media/folders/${id}`)
}

export async function getFolderTree(): Promise<FolderTreeItem[]> {
  const response = await api.get('/media/folders/tree')
  return response.data
}

export async function listAssets(query: AssetListQuery = {}): Promise<AssetListResponse> {
  const response = await api.get('/media/assets', { params: query })
  return response.data
}

export async function getAsset(id: string): Promise<MediaAsset> {
  const response = await api.get(`/media/assets/${id}`)
  return response.data
}

export async function updateAsset(id: string, payload: AssetUpdatePayload): Promise<MediaAsset> {
  const response = await api.patch(`/media/assets/${id}`, payload)
  return response.data
}

export async function deleteAsset(id: string): Promise<void> {
  await api.delete(`/media/assets/${id}`)
}

export async function uploadAssets(
  files: File[],
  folderId?: string,
  onProgress?: (progress: UploadProgress) => void
): Promise<MediaAsset[]> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  if (folderId) {
    formData.append('folder_id', folderId)
  }

  const response = await api.post('/media/assets/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        onProgress({
          loaded: progressEvent.loaded,
          total: progressEvent.total,
          percentage: Math.round((progressEvent.loaded * 100) / progressEvent.total),
        })
      }
    },
  })
  return response.data.assets
}

export async function regeneratePreview(id: string, request: PreviewFrameRequest): Promise<MediaAsset> {
  const response = await api.post(`/media/assets/${id}/preview`, request)
  return response.data
}

export async function listTags(): Promise<MediaTag[]> {
  const response = await api.get('/media/tags')
  return response.data
}

export async function createTag(payload: { name: string; color: string }): Promise<MediaTag> {
  const response = await api.post('/media/tags', payload)
  return response.data
}

export async function updateTag(id: string, payload: { name?: string; color?: string }): Promise<MediaTag> {
  const response = await api.patch(`/media/tags/${id}`, payload)
  return response.data
}

export async function deleteTag(id: string): Promise<void> {
  await api.delete(`/media/tags/${id}`)
}

export async function bulkMoveAssets(request: BulkMoveRequest): Promise<{ moved: number }> {
  const response = await api.post('/media/assets/bulk/move', request)
  return response.data
}

export async function bulkDeleteAssets(request: BulkDeleteRequest): Promise<{ deleted: number }> {
  const response = await api.post('/media/assets/bulk/delete', request)
  return response.data
}

export async function bulkTagAssets(request: BulkTagRequest): Promise<{ tagged: number }> {
  const response = await api.post('/media/assets/bulk/tag', request)
  return response.data
}

export function getAssetUrl(assetPath: string): string {
  if (assetPath.startsWith('http')) {
    return assetPath
  }
  return `/api/media/assets/raw/${assetPath}`
}

export function getPreviewUrl(assetId: string): string {
  return `/api/media/assets/${assetId}/preview`
}
