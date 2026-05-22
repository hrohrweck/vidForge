export type FileType = 'image' | 'video' | 'markdown' | 'audio'
export type SourceType = 'generated' | 'uploaded'

export interface MediaFolder {
  id: string
  user_id: string
  parent_id: string | null
  name: string
  created_at: string
  updated_at: string
}

export interface FolderTreeItem extends MediaFolder {
  children: FolderTreeItem[]
}

export interface MediaAsset {
  id: string
  user_id: string
  project_id?: string
  folder_id: string | null
  name: string
  file_path: string
  file_type: FileType
  mime_type: string | null
  size_bytes: number | null
  preview_path: string | null
  source_type: SourceType
  source_job_id: string | null
  asset_metadata: Record<string, unknown> | null
  created_at: string
  updated_at: string
  tags: MediaTag[]
}

export interface AssetListQuery {
  project_id?: string
  folder_id?: string
  cursor?: string
  limit?: number
  file_type?: FileType
  source_type?: SourceType
  tag_ids?: string[]
  search?: string
  sort_by?: 'created_at' | 'name' | 'size_bytes'
  sort_order?: 'asc' | 'desc'
}

export interface AssetListResponse {
  assets: MediaAsset[]
  next_cursor: string | null
  total_count: number | null
}

export interface AssetUpdatePayload {
  name?: string
  project_id?: string
  folder_id?: string | null
  tag_ids?: string[]
}

export interface PreviewFrameRequest {
  timestamp_seconds: number
}

export interface MediaTag {
  id: string
  user_id: string
  name: string
  color: string
  created_at: string
}

export interface BulkMoveRequest {
  asset_ids: string[]
  target_folder_id: string | null
}

export interface BulkDeleteRequest {
  asset_ids: string[]
}

export interface BulkTagRequest {
  asset_ids: string[]
  tag_ids: string[]
}

export interface BulkDownloadRequest {
  asset_ids: string[]
}

export interface UploadProgress {
  loaded: number
  total: number
  percentage: number
}

export interface StorageStats {
  total_assets: number
  total_size_bytes: number
  total_folders: number
}

export interface DeleteRefusedError extends Error {
  referrer_assets?: MediaAsset[]
  folder_contents?: MediaAsset[]
}
