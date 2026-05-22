import { useEffect, useRef, useCallback } from 'react'
import type { MediaAsset } from '../../api/types/media'
import { MediaTile } from './MediaTile'
import type { UseMediaSelectionReturn } from '../../hooks/useMediaSelection'

export type CanvasView = 'grid' | 'list' | 'masonry'

export interface MediaCanvasProps {
  assets: MediaAsset[]
  view: CanvasView
  selection: UseMediaSelectionReturn
  onAssetClick?: (asset: MediaAsset) => void
  onAssetDoubleClick?: (asset: MediaAsset) => void
  onContextMenu?: (asset: MediaAsset, event: React.MouseEvent) => void
  isLoading?: boolean
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  onLoadMore?: () => void
}

/**
 * Loading skeleton for grid view
 */
function GridSkeleton() {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] auto-rows-auto gap-3 p-6">
      {Array.from({ length: 12 }).map((_, i) => (
        <div
          key={i}
          className="bg-card rounded-lg border border-border overflow-hidden animate-pulse"
        >
          <div className="aspect-video bg-muted" />
          <div className="p-3 space-y-2">
            <div className="h-4 bg-muted rounded w-3/4" />
            <div className="h-3 bg-muted rounded w-1/2" />
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * Loading skeleton for list view
 */
function ListSkeleton() {
  return (
    <div className="p-6">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border">
            <th className="w-12 p-3" />
            <th className="w-20 p-3" />
            <th className="text-left p-3">Name</th>
            <th className="w-24 p-3">Type</th>
            <th className="w-24 p-3">Size</th>
            <th className="w-32 p-3">Created</th>
            <th className="w-12 p-3" />
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 8 }).map((_, i) => (
            <tr key={i} className="border-b border-border animate-pulse">
              <td className="p-3">
                <div className="h-4 w-4 bg-muted rounded" />
              </td>
              <td className="p-3">
                <div className="h-12 w-16 bg-muted rounded" />
              </td>
              <td className="p-3">
                <div className="h-4 bg-muted rounded w-48" />
              </td>
              <td className="p-3">
                <div className="h-4 bg-muted rounded w-16" />
              </td>
              <td className="p-3">
                <div className="h-4 bg-muted rounded w-20" />
              </td>
              <td className="p-3">
                <div className="h-4 bg-muted rounded w-24" />
              </td>
              <td className="p-3" />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Loading skeleton for masonry view
 */
function MasonrySkeleton() {
  return (
    <div className="columns-2 sm:columns-3 md:columns-4 lg:columns-5 xl:columns-6 gap-3 p-6">
      {Array.from({ length: 12 }).map((_, i) => (
        <div
          key={i}
          className="break-inside-avoid mb-3 bg-card rounded-lg border border-border overflow-hidden animate-pulse"
        >
          <div className="aspect-square bg-muted" />
          <div className="p-3 space-y-2">
            <div className="h-4 bg-muted rounded w-3/4" />
            <div className="h-3 bg-muted rounded w-1/2" />
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * Empty state component
 */
function EmptyState({ view }: { view: CanvasView }) {
  const isList = view === 'list'

  return (
    <div
      className={`flex flex-col items-center justify-center ${
        isList ? 'h-96' : 'h-64'
      } text-muted-foreground`}
    >
      <div className="text-lg font-medium">No assets found</div>
      <div className="text-sm mt-1">Upload files or generate new content to get started</div>
    </div>
  )
}

/**
 * Renders a row for list view
 */
function MediaListRow({
  asset,
  selected,
  selection,
  onAssetClick,
  onAssetDoubleClick,
  onContextMenu,
  orderedIds,
}: {
  asset: MediaAsset
  selected: boolean
  selection: UseMediaSelectionReturn
  onAssetClick?: (asset: MediaAsset) => void
  onAssetDoubleClick?: (asset: MediaAsset) => void
  onContextMenu?: (asset: MediaAsset, event: React.MouseEvent) => void
  orderedIds: string[]
}) {
  const { selectOnly, toggle, range } = selection

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.detail === 2) {
        onAssetDoubleClick?.(asset)
        return
      }

      if (e.ctrlKey || e.metaKey) {
        toggle(asset.id)
      } else if (e.shiftKey) {
        range(asset.id, orderedIds)
      } else {
        selectOnly(asset.id)
      }

      onAssetClick?.(asset)
    },
    [asset, toggle, range, selectOnly, onAssetClick, onAssetDoubleClick, orderedIds]
  )

  const handleCheckboxChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      e.stopPropagation()
      if (e.target.checked) {
        selectOnly(asset.id)
      } else {
        toggle(asset.id)
      }
    },
    [asset.id, selectOnly, toggle]
  )

  const formatSize = (bytes: number | null) => {
    if (bytes === null) return '—'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  }

  const previewUrl = asset.preview_path
    ? `/api/media/assets/${asset.id}/preview`
    : asset.file_type === 'image'
    ? `/api/media/assets/${asset.id}`
    : undefined

  return (
    <tr
      className={`border-b border-border cursor-pointer transition-colors ${
        selected ? 'bg-primary/10' : 'hover:bg-muted/50'
      }`}
      onClick={handleClick}
      onContextMenu={onContextMenu ? (e) => onContextMenu(asset, e) : undefined}
    >
      <td className="p-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={handleCheckboxChange}
          onClick={(e) => e.stopPropagation()}
          className="h-4 w-4 rounded border-border"
        />
      </td>
      <td className="p-3">
        <div className="h-12 w-16 bg-muted rounded overflow-hidden flex items-center justify-center">
          {previewUrl && asset.file_type === 'image' ? (
            <img src={previewUrl} alt="" className="h-full w-full object-cover" />
          ) : asset.file_type === 'video' ? (
            <div className="text-xs text-muted-foreground">Video</div>
          ) : (
            <div className="text-xs text-muted-foreground capitalize">{asset.file_type}</div>
          )}
        </div>
      </td>
      <td className="p-3 font-medium text-foreground truncate max-w-xs">{asset.name}</td>
      <td className="p-3 text-sm text-muted-foreground capitalize">{asset.file_type}</td>
      <td className="p-3 text-sm text-muted-foreground">{formatSize(asset.size_bytes)}</td>
      <td className="p-3 text-sm text-muted-foreground">{formatDate(asset.created_at)}</td>
      <td className="p-3" />
    </tr>
  )
}

/**
 * Main MediaCanvas component
 * Displays assets in grid, list, or masonry view with selection support
 */
export function MediaCanvas({
  assets,
  view,
  selection,
  onAssetClick,
  onAssetDoubleClick,
  onContextMenu,
  isLoading = false,
  hasNextPage = false,
  isFetchingNextPage = false,
  onLoadMore,
}: MediaCanvasProps) {
  const loadMoreRef = useRef<HTMLDivElement>(null)

  const handleIntersection = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
        onLoadMore?.()
      }
    },
    [hasNextPage, isFetchingNextPage, onLoadMore]
  )

  useEffect(() => {
    const observer = new IntersectionObserver(handleIntersection, {
      root: null,
      rootMargin: '100px',
      threshold: 0.1,
    })

    if (loadMoreRef.current) {
      observer.observe(loadMoreRef.current)
    }

    return () => observer.disconnect()
  }, [handleIntersection])

  // Show skeletons when loading
  if (isLoading) {
    if (view === 'list') {
      return <ListSkeleton />
    }
    if (view === 'masonry') {
      return <MasonrySkeleton />
    }
    return <GridSkeleton />
  }

  // Show empty state when no assets
  if (assets.length === 0) {
    return <EmptyState view={view} />
  }

  // Grid View
  if (view === 'grid') {
    return (
      <>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] auto-rows-auto gap-3 p-6">
          {assets.map((asset) => (
            <MediaTile
              key={asset.id}
              asset={asset}
              selected={selection.isSelected(asset.id)}
              onSelectOnly={selection.selectOnly}
              onToggle={selection.toggle}
              onRange={(toId) => selection.range(toId, assets.map((a) => a.id))}
              onMoreClick={onAssetClick ? (a) => onAssetClick(a) : undefined}
              onContextMenu={onContextMenu}
            />
          ))}
        </div>

        {/* Infinite scroll sentinel */}
        <div ref={loadMoreRef} className="h-10 flex items-center justify-center">
          {isFetchingNextPage && (
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary" />
          )}
        </div>
      </>
    )
  }

  // List View
  if (view === 'list') {
    return (
      <>
        <div className="p-6">
          <table className="w-full">
            <thead className="sticky top-0 bg-background z-10">
              <tr className="border-b border-border">
                <th className="w-12 p-3">
                  <input
                    type="checkbox"
                    checked={selection.count === assets.length && assets.length > 0}
                    onChange={() => {
                      if (selection.count === assets.length) {
                        selection.clear()
                      } else {
                        selection.selectAll(assets.map((a) => a.id))
                      }
                    }}
                    className="h-4 w-4 rounded border-border"
                  />
                </th>
                <th className="w-20 p-3">Preview</th>
                <th className="text-left p-3 cursor-pointer hover:text-foreground">Name</th>
                <th className="w-24 p-3 cursor-pointer hover:text-foreground">Type</th>
                <th className="w-24 p-3 cursor-pointer hover:text-foreground">Size</th>
                <th className="w-32 p-3 cursor-pointer hover:text-foreground">Created</th>
                <th className="w-12 p-3" />
              </tr>
            </thead>
            <tbody>
              {assets.map((asset) => (
                <MediaListRow
                  key={asset.id}
                  asset={asset}
                  selected={selection.isSelected(asset.id)}
                  selection={selection}
                  onAssetClick={onAssetClick}
                  onAssetDoubleClick={onAssetDoubleClick}
                  onContextMenu={onContextMenu}
                  orderedIds={assets.map((a) => a.id)}
                />
              ))}
            </tbody>
          </table>
        </div>

        {/* Infinite scroll sentinel */}
        <div ref={loadMoreRef} className="h-10 flex items-center justify-center">
          {isFetchingNextPage && (
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary" />
          )}
        </div>
      </>
    )
  }

  // Masonry View
  if (view === 'masonry') {
    return (
      <>
        <div className="columns-2 sm:columns-3 md:columns-4 lg:columns-5 xl:columns-6 gap-3 p-6">
          {assets.map((asset) => (
            <div key={asset.id} className="break-inside-avoid mb-3">
              <MediaTile
                asset={asset}
                selected={selection.isSelected(asset.id)}
                onSelectOnly={selection.selectOnly}
                onToggle={selection.toggle}
                onRange={(toId) => selection.range(toId, assets.map((a) => a.id))}
                onMoreClick={onAssetClick ? (a) => onAssetClick(a) : undefined}
                onContextMenu={onContextMenu}
              />
            </div>
          ))}
        </div>

        {/* Infinite scroll sentinel */}
        <div ref={loadMoreRef} className="h-10 flex items-center justify-center">
          {isFetchingNextPage && (
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary" />
          )}
        </div>
      </>
    )
  }

  return null
}
