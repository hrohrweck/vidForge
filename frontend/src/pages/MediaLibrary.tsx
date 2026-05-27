import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { DndContext } from '@dnd-kit/core'
import { FolderRail } from '../components/media/FolderRail'
import { MediaCanvas } from '../components/media/MediaCanvas'
import { MediaToolbar } from '../components/media/MediaToolbar'
import { BulkActionsBar } from '../components/media/BulkActionsBar'
import { MediaDetailPanel } from '../components/media/MediaDetailPanel'
import { MediaContextMenu } from '../components/media/MediaContextMenu'
import { Lightbox } from '../components/media/Lightbox'
import { UploadDropzone } from '../components/media/UploadDropzone'
import { useFolderDnD } from '../hooks/useFolderDnD'
import { useMediaKeyboard } from '../hooks/useMediaKeyboard'
import { useMediaSelection } from '../hooks/useMediaSelection'
import { useBulkMoveAssets, useBulkDeleteAssets, useUploadAssets, useAssets, useFolderTree, useCreateFolder, useUpdateFolder, useDeleteFolder } from '../hooks/useMedia'
import type { MediaAsset, AssetListQuery } from '../api/types/media'

export function MediaLibrary() {
  const navigate = useNavigate()
  
  // State
  const [selectedFolderId, setSelectedFolderId] = useState<string | undefined>()
  const [view, setView] = useState<'grid' | 'list' | 'masonry'>('grid')
  const [query, setQuery] = useState<AssetListQuery>({
    folder_id: selectedFolderId,
    limit: 50,
  })
  
  // Selection
  const selection = useMediaSelection()
  
  // Context menu state
  const [contextMenuAsset, setContextMenuAsset] = useState<MediaAsset | null>(null)
  const [contextMenuPosition, setContextMenuPosition] = useState<{ x: number; y: number } | null>(null)
  const [isContextMenuOpen, setIsContextMenuOpen] = useState(false)
  
  // Lightbox state
  const [lightboxIndex, setLightboxIndex] = useState(0)
  const [isLightboxOpen, setIsLightboxOpen] = useState(false)
  
  // Detail panel state
  const [selectedAssetForDetails, setSelectedAssetForDetails] = useState<MediaAsset | null>(null)
  const [isDetailPanelOpen, setIsDetailPanelOpen] = useState(false)
  
  // Upload state
  const [isUploadDropzoneOpen, setIsUploadDropzoneOpen] = useState(false)

  // Data
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } = useAssets(query)
  const allAssets = data?.pages.flatMap((page) => page.assets) ?? []

  // Hooks
  const bulkMoveMutation = useBulkMoveAssets()
  const bulkDeleteMutation = useBulkDeleteAssets()
  const uploadMutation = useUploadAssets()

  // Folder tree data and CRUD
  const { data: folderTree = [] } = useFolderTree()
  const createFolderMutation = useCreateFolder()
  const updateFolderMutation = useUpdateFolder()
  const deleteFolderMutation = useDeleteFolder()

  // Folder CRUD handlers
  const handleCreateFolder = useCallback((name: string, parentId: string | null) => {
    createFolderMutation.mutate({ name, parent_id: parentId ?? undefined })
  }, [createFolderMutation])

  const handleUpdateFolder = useCallback((id: string, payload: { name: string }) => {
    updateFolderMutation.mutate({ id, payload })
  }, [updateFolderMutation])

  const handleDeleteFolder = useCallback((id: string) => {
    if (window.confirm('Are you sure you want to delete this folder and all its contents?')) {
      deleteFolderMutation.mutate(id)
      if (selectedFolderId === id) {
        setSelectedFolderId(undefined)
        setQuery((prev) => ({ ...prev, folder_id: undefined }))
      }
    }
  }, [deleteFolderMutation, selectedFolderId])

  // Drag and drop
  const {
    activeId: _activeId,
    overId: _overId,
    handleDragStart,
    handleDragOver,
    handleDragEnd,
    handleDragCancel,
  } = useFolderDnD({
    onMoveAssets: async (assetIds, targetFolderId) => {
      await bulkMoveMutation.mutateAsync({
        asset_ids: assetIds,
        target_folder_id: targetFolderId,
      })
      selection.clear()
    },
  })

  // Keyboard shortcuts
  useMediaKeyboard({
    selectedAssets: selection.selectedIds,
    allAssetIds: allAssets.map((a) => a.id),
    onSelectAll: () => selection.selectAll(allAssets.map((a) => a.id)),
    onDelete: () => {
      if (selection.count > 0) {
        handleBulkDelete()
      }
    },
    onRename: () => {},
    onEscape: () => {
      setIsContextMenuOpen(false)
      selection.clear()
    },
    enabled: true,
  })

  // Handlers
  const handleAssetClick = useCallback((asset: MediaAsset) => {
    setSelectedAssetForDetails(asset)
    setIsDetailPanelOpen(true)
  }, [])

  const handleAssetDoubleClick = useCallback((asset: MediaAsset) => {
    setSelectedAssetForDetails(asset)
    setIsDetailPanelOpen(true)
  }, [])

  const handleContextMenu = useCallback((asset: MediaAsset, event: React.MouseEvent) => {
    event.preventDefault()
    setContextMenuAsset(asset)
    setContextMenuPosition({ x: event.clientX, y: event.clientY })
    setIsContextMenuOpen(true)
  }, [])

  const handleBulkDelete = useCallback(async () => {
    if (selection.count === 0) return
    
    const confirmed = window.confirm(
      `Are you sure you want to delete ${selection.count} asset(s)?`
    )
    
    if (confirmed) {
      await bulkDeleteMutation.mutateAsync({
        asset_ids: Array.from(selection.selectedIds),
      })
      selection.clear()
    }
  }, [selection, bulkDeleteMutation])

  const handleUpload = useCallback(async (files: File[]) => {
    await uploadMutation.mutateAsync({
      files,
      folderId: selectedFolderId,
    })
  }, [uploadMutation, selectedFolderId])

  const handleQueryChange = useCallback((newQuery: Partial<AssetListQuery>) => {
    setQuery((prev) => ({ ...prev, ...newQuery }))
  }, [])

  const handleFolderChange = useCallback((folderId: string | undefined) => {
    setSelectedFolderId(folderId)
    setQuery((prev) => ({ ...prev, folder_id: folderId }))
    selection.clear()
  }, [selection])

  const handleRenameAsset = useCallback((_asset: MediaAsset) => {}, [])

  const handleDeleteAsset = useCallback((asset: MediaAsset) => {
    selection.selectOnly(asset.id)
    handleBulkDelete()
  }, [selection, handleBulkDelete])

  const handleDownloadAsset = useCallback((asset: MediaAsset) => {
    window.open(`/api/media/assets/${asset.id}/file?download=1`, '_blank')
  }, [])

  const handleUseInProject = useCallback((asset: MediaAsset) => {
    navigate(`/editor?asset=${asset.id}`)
  }, [navigate])

  const handleCopyUrl = useCallback((asset: MediaAsset) => {
    const url = `${window.location.origin}/api/media/assets/${asset.id}/file`
    navigator.clipboard.writeText(url)
  }, [])

  const handleOpenInNewTab = useCallback((asset: MediaAsset) => {
    window.open(`/api/media/assets/${asset.id}/file`, '_blank')
  }, [])

  // Render
  return (
    <DndContext
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
      onDragCancel={handleDragCancel}
    >
      <div className="flex h-full gap-[10px] p-[10px]">
        {/* Left Sidebar - Folder Rail */}
        <div className="w-56 shrink-0 rounded-[10px] border bg-card overflow-hidden flex flex-col h-full">
          <FolderRail
            folders={folderTree}
            selectedId={selectedFolderId}
            onSelect={handleFolderChange}
            onCreateFolder={handleCreateFolder}
            onUpdateFolder={handleUpdateFolder}
            onDeleteFolder={handleDeleteFolder}
            maxDepth={3}
          />
        </div>

        {/* Main Content */}
        <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden gap-[10px] relative">
          {/* Toolbar */}
          <MediaToolbar
            query={query}
            onQueryChange={handleQueryChange}
            view={view}
            onViewChange={(v) => setView(v as 'grid' | 'list' | 'masonry')}
            onUploadClick={() => setIsUploadDropzoneOpen(true)}
            breadcrumbs={[{ id: null, name: 'All Assets' }, ...(selectedFolderId ? [{ id: selectedFolderId, name: 'Current Folder' }] : [])]}
          />

          {/* Canvas */}
          <div className="flex-1 overflow-y-auto min-h-0">
            {/* Bulk Actions Bar - slides down centered at top */}
            <BulkActionsBar
              selection={selection}
              onMove={() => {}}
              onTag={() => {}}
              onDelete={handleBulkDelete}
            />
            <MediaCanvas
              assets={allAssets}
              view={view}
              selection={selection}
              onAssetClick={handleAssetClick}
              onAssetDoubleClick={handleAssetDoubleClick}
              onContextMenu={handleContextMenu}
              isLoading={isLoading}
              hasNextPage={hasNextPage}
              isFetchingNextPage={isFetchingNextPage}
              onLoadMore={() => fetchNextPage()}
            />
          </div>
        </div>

        {/* Right Sidebar - Detail Panel */}
        {isDetailPanelOpen && selectedAssetForDetails && (
          <div className="w-80 shrink-0 rounded-[10px] border bg-card overflow-hidden h-full">
            <MediaDetailPanel
              asset={selectedAssetForDetails}
              isOpen={isDetailPanelOpen}
              onClose={() => setIsDetailPanelOpen(false)}
            />
          </div>
        )}
      </div>

      {/* Context Menu */}
      <MediaContextMenu
        asset={contextMenuAsset}
        position={contextMenuPosition}
        isOpen={isContextMenuOpen}
        onClose={() => setIsContextMenuOpen(false)}
        onRename={handleRenameAsset}
        onDelete={handleDeleteAsset}
        onDownload={handleDownloadAsset}
        onUseInProject={handleUseInProject}
        onCopyUrl={handleCopyUrl}
        onOpenInNewTab={handleOpenInNewTab}
      />

      {/* Lightbox */}
      <Lightbox
        assets={allAssets}
        currentIndex={lightboxIndex}
        isOpen={isLightboxOpen}
        onClose={() => setIsLightboxOpen(false)}
        onNavigate={setLightboxIndex}
      />

      {/* Upload Dropzone */}
      <UploadDropzone
        isOpen={isUploadDropzoneOpen}
        onClose={() => setIsUploadDropzoneOpen(false)}
        onFilesSelected={handleUpload}
      />
    </DndContext>
  )
}
