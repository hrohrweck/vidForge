import { useState, useRef, useCallback } from 'react'
import type { MediaAsset } from '../../api/types/media'
import { getPreviewUrl, getAssetUrl } from '../../api/media'

interface MediaThumbnailProps {
  asset: MediaAsset
  size?: number
  onClick?: (asset: MediaAsset) => void
  selected?: boolean
  selectable?: boolean
  onSelect?: (asset: MediaAsset, selected: boolean) => void
}

export function MediaThumbnail({
  asset,
  size = 200,
  onClick,
  selected = false,
  selectable = false,
  onSelect,
}: MediaThumbnailProps) {
  const [isHovered, setIsHovered] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)

  const handleMouseEnter = useCallback(() => {
    setIsHovered(true)
    if (asset.file_type === 'video' && videoRef.current) {
      videoRef.current.play().catch(() => {
        // Autoplay might be blocked, ignore error
      })
    }
  }, [asset.file_type])

  const handleMouseLeave = useCallback(() => {
    setIsHovered(false)
    if (asset.file_type === 'video' && videoRef.current) {
      videoRef.current.pause()
      videoRef.current.currentTime = 0
    }
  }, [asset.file_type])

  const handleClick = (e: React.MouseEvent) => {
    if (selectable && (e.ctrlKey || e.metaKey || e.shiftKey)) {
      e.preventDefault()
      onSelect?.(asset, !selected)
    } else {
      onClick?.(asset)
    }
  }

  const previewUrl = asset.preview_path
    ? getPreviewUrl(asset.id)
    : asset.file_type === 'image'
    ? getAssetUrl(asset.file_path)
    : undefined

  return (
    <div
      className={`relative rounded-lg overflow-hidden cursor-pointer transition-all ${
        selected ? 'ring-2 ring-primary' : 'hover:ring-2 hover:ring-border'
      }`}
      style={{ width: size, height: size }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      {asset.file_type === 'video' && isHovered ? (
        <video
          ref={videoRef}
          src={getAssetUrl(asset.file_path)}
          className="w-full h-full object-cover"
          muted
          loop
          playsInline
        />
      ) : previewUrl ? (
        <img
          src={previewUrl}
          alt={asset.name}
          className="w-full h-full object-cover"
          loading="lazy"
        />
      ) : (
        <div className="w-full h-full bg-muted flex items-center justify-center">
          <span className="text-4xl">
            {asset.file_type === 'video' && '🎬'}
            {asset.file_type === 'audio' && '🎵'}
            {asset.file_type === 'markdown' && '📝'}
            {asset.file_type === 'image' && '🖼️'}
          </span>
        </div>
      )}

      {/* Overlay with name */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-2">
        <p className="text-white text-sm truncate">{asset.name}</p>
      </div>

      {/* Type indicator */}
      <div className="absolute top-2 right-2 bg-black/50 text-white text-xs px-1.5 py-0.5 rounded">
        {asset.file_type}
      </div>

      {/* Selection checkbox */}
      {selectable && (
        <div className="absolute top-2 left-2">
          <input
            type="checkbox"
            checked={selected}
            onChange={(e) => onSelect?.(asset, e.target.checked)}
            className="w-4 h-4 rounded border-input text-primary focus:ring-ring"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  )
}
