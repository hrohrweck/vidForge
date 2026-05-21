import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from '@tanstack/react-query'
import * as mediaApi from '../api/media'
import type {
  AssetListQuery,
  AssetUpdatePayload,
  PreviewFrameRequest,
} from '../api/types/media'

// Query keys
export const mediaKeys = {
  all: ['media'] as const,
  folders: () => [...mediaKeys.all, 'folders'] as const,
  folderTree: () => [...mediaKeys.all, 'folderTree'] as const,
  assets: (query: AssetListQuery) => [...mediaKeys.all, 'assets', query] as const,
  asset: (id: string) => [...mediaKeys.all, 'asset', id] as const,
  tags: () => [...mediaKeys.all, 'tags'] as const,
}

// Folder hooks
export function useFolders(parentId?: string) {
  return useQuery({
    queryKey: mediaKeys.folders(),
    queryFn: () => mediaApi.listFolders(parentId),
  })
}

export function useFolderTree() {
  return useQuery({
    queryKey: mediaKeys.folderTree(),
    queryFn: () => mediaApi.getFolderTree(),
  })
}

export function useCreateFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: mediaApi.createFolder,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.folders() })
      queryClient.invalidateQueries({ queryKey: mediaKeys.folderTree() })
    },
  })
}

export function useUpdateFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof mediaApi.updateFolder>[1] }) =>
      mediaApi.updateFolder(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.folders() })
      queryClient.invalidateQueries({ queryKey: mediaKeys.folderTree() })
    },
  })
}

export function useDeleteFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: mediaApi.deleteFolder,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.folders() })
      queryClient.invalidateQueries({ queryKey: mediaKeys.folderTree() })
    },
  })
}

// Asset hooks
export function useAssets(query: AssetListQuery = {}) {
  return useInfiniteQuery({
    queryKey: mediaKeys.assets(query),
    queryFn: ({ pageParam }) =>
      mediaApi.listAssets({ ...query, cursor: pageParam }),
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    initialPageParam: undefined as string | undefined,
  })
}

export function useAsset(id: string) {
  return useQuery({
    queryKey: mediaKeys.asset(id),
    queryFn: () => mediaApi.getAsset(id),
    enabled: !!id,
  })
}

export function useUpdateAsset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: AssetUpdatePayload }) =>
      mediaApi.updateAsset(id, payload),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.assets({}) })
      queryClient.invalidateQueries({ queryKey: mediaKeys.asset(data.id) })
    },
  })
}

export function useDeleteAsset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: mediaApi.deleteAsset,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.assets({}) })
    },
  })
}

export function useUploadAssets() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      files,
      folderId,
      onProgress,
    }: {
      files: File[]
      folderId?: string
      onProgress?: Parameters<typeof mediaApi.uploadAssets>[2]
    }) => mediaApi.uploadAssets(files, folderId, onProgress),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.assets({}) })
    },
  })
}

export function useRegeneratePreview() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, request }: { id: string; request: PreviewFrameRequest }) =>
      mediaApi.regeneratePreview(id, request),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.asset(data.id) })
      queryClient.invalidateQueries({ queryKey: mediaKeys.assets({}) })
    },
  })
}

// Tag hooks
export function useTags() {
  return useQuery({
    queryKey: mediaKeys.tags(),
    queryFn: () => mediaApi.listTags(),
  })
}

export function useCreateTag() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: mediaApi.createTag,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.tags() })
    },
  })
}

export function useUpdateTag() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof mediaApi.updateTag>[1] }) =>
      mediaApi.updateTag(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.tags() })
    },
  })
}

export function useDeleteTag() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: mediaApi.deleteTag,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.tags() })
      queryClient.invalidateQueries({ queryKey: mediaKeys.assets({}) })
    },
  })
}

// Bulk operation hooks
export function useBulkMoveAssets() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: mediaApi.bulkMoveAssets,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.assets({}) })
      queryClient.invalidateQueries({ queryKey: mediaKeys.folders() })
    },
  })
}

export function useBulkDeleteAssets() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: mediaApi.bulkDeleteAssets,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.assets({}) })
    },
  })
}

export function useBulkTagAssets() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: mediaApi.bulkTagAssets,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mediaKeys.assets({}) })
      queryClient.invalidateQueries({ queryKey: mediaKeys.tags() })
    },
  })
}
