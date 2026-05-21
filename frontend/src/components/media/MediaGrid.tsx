import { useEffect, useRef, useCallback } from 'react'
import { useAssets } from '../../hooks/useMedia'
import type { MediaAsset, AssetListQuery } from '../../api/types/media'
import { MediaThumbnail } from './MediaThumbnail'

interface MediaGridProps {
  query?: AssetListQuery
  selectedAssets?: Set<string>
  onSelectAsset?: (asset: MediaAsset, selected: boolean) => void
  onAssetClick?: (asset: MediaAsset) => void
  selectable?: boolean
}

export function MediaGrid({
  query = {},
  selectedAssets = new Set(),
  onSelectAsset,
  onAssetClick,
  selectable = false,
}: MediaGridProps) {
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading, error } =
    useAssets(query)

  const loadMoreRef = useRef<HTMLDivElement>(null)

  const handleIntersection = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
        fetchNextPage()
      }
    },
    [fetchNextPage, hasNextPage, isFetchingNextPage]
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

  const allAssets = data?.pages.flatMap((page) => page.assets) ?? []

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-destructive">
        Error loading assets: {error.message}
      </div>
    )
  }

  if (allAssets.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        No assets found
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
        {allAssets.map((asset) => (
          <MediaThumbnail
            key={asset.id}
            asset={asset}
            selected={selectedAssets.has(asset.id)}
            selectable={selectable}
            onSelect={onSelectAsset}
            onClick={onAssetClick}
          />
        ))}
      </div>

      {/* Infinite scroll sentinel */}
      <div ref={loadMoreRef} className="h-10 flex items-center justify-center">
        {isFetchingNextPage && (
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary" />
        )}
      </div>
    </div>
  )
}
