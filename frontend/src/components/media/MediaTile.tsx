import { useState, useRef, useCallback, useEffect } from 'react'
import type { MediaAsset } from '../../api/types/media'
import { getPreviewUrl, getAssetUrl } from '../../api/media'
import { Volume2, VolumeX, MoreHorizontal } from 'lucide-react'

export interface MediaTileProps {
  asset: MediaAsset
  selected?: boolean
  onSelect?: (id: string, selected: boolean, event?: React.MouseEvent) => void
  onToggle?: (id: string) => void
  onRange?: (toId: string, orderedIds?: string[]) => void
  onSelectOnly?: (id: string) => void
  onAssetClick?: (asset: MediaAsset) => void
  onAssetDoubleClick?: (asset: MediaAsset) => void
  onRename?: (id: string, newName: string) => Promise<void>
  onMoreClick?: (asset: MediaAsset, event: React.MouseEvent) => void
  onContextMenu?: (asset: MediaAsset, event: React.MouseEvent) => void
}

/**
 * Computes aspect ratio from asset metadata.
 * Falls back to 16:9 for video, 1:1 for images.
 */
function getAspectRatio(asset: MediaAsset): string {
  const metadata = asset.asset_metadata as Record<string, unknown> | null
  const width = metadata?.width as number | undefined
  const height = metadata?.height as number | undefined

  if (width && height && width > 0 && height > 0) {
    return `${width} / ${height}`
  }

  // Fallback based on file type
  if (asset.file_type === 'video') {
    return '16 / 9'
  }

  // Default to square for images and other types
  return '1 / 1'
}

export function MediaTile({
  asset,
  selected = false,
  onSelect,
  onToggle,
  onRange,
  onSelectOnly,
  onAssetClick,
  onAssetDoubleClick,
  onRename,
  onMoreClick,
  onContextMenu,
}: MediaTileProps) {
  const [isHovered, setIsHovered] = useState(false)
  const [isMuted, setIsMuted] = useState(true)
  const [isEditing, setIsEditing] = useState(false)
  const [editName, setEditName] = useState(asset.name)
  const videoRef = useRef<HTMLVideoElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const aspectRatio = getAspectRatio(asset)
  const previewUrl = asset.preview_path
    ? getPreviewUrl(asset.id)
    : asset.file_type === 'image'
    ? getAssetUrl(asset)
    : undefined

  const isVideo = asset.file_type === 'video'

  // Focus input when editing starts
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [isEditing])

  const handleMouseEnter = useCallback(() => {
    setIsHovered(true)
    if (isVideo && videoRef.current) {
      videoRef.current.play().catch(() => {
        // Autoplay might be blocked, ignore error
      })
    }
  }, [isVideo])

  const handleMouseLeave = useCallback(() => {
    setIsHovered(false)
    if (isVideo && videoRef.current) {
      videoRef.current.pause()
      videoRef.current.currentTime = 0
    }
  }, [isVideo])

  const handleVolumeToggle = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    e.preventDefault()
    setIsMuted(prev => {
      const newMuted = !prev
      if (videoRef.current) {
        videoRef.current.muted = newMuted
      }
      return newMuted
    })
  }, [])

  const handleMoreClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    e.preventDefault()
    onMoreClick?.(asset, e)
  }, [asset, onMoreClick])

  const handleClick = useCallback((e: React.MouseEvent) => {
    if (onSelectOnly && onToggle && onRange) {
      // Use the selection handlers if provided (for multi-select support)
      if (e.ctrlKey || e.metaKey) {
        onToggle(asset.id)
      } else if (e.shiftKey) {
        onRange(asset.id)
      } else {
        onSelectOnly(asset.id)
        onAssetClick?.(asset)
      }
    } else if (onSelect) {
      // Fallback to simple onSelect
      onSelect(asset.id, !selected, e)
    }
  }, [asset, asset.id, selected, onSelect, onSelectOnly, onToggle, onRange, onAssetClick])

  const handleCheckboxChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    e.stopPropagation()
    if (onToggle) {
      onToggle(asset.id)
    } else if (onSelect) {
      onSelect(asset.id, e.target.checked, e as unknown as React.MouseEvent)
    }
  }, [asset.id, onSelect, onToggle])

  const handleDoubleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    onAssetDoubleClick?.(asset)
  }, [asset, onAssetDoubleClick])

  const handleNameDoubleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    e.preventDefault()
    if (onRename) {
      setIsEditing(true)
      setEditName(asset.name)
    }
  }, [onRename, asset.name])

  const handleNameSubmit = useCallback(async () => {
    if (editName.trim() && editName.trim() !== asset.name) {
      await onRename?.(asset.id, editName.trim())
    } else {
      setEditName(asset.name)
    }
    setIsEditing(false)
  }, [editName, asset.id, asset.name, onRename])

  const handleNameKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleNameSubmit()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setEditName(asset.name)
      setIsEditing(false)
    }
  }, [handleNameSubmit, asset.name])

  const handleNameBlur = useCallback(() => {
    handleNameSubmit()
  }, [handleNameSubmit])

  const getFileTypeIcon = () => {
    switch (asset.file_type) {
      case 'video':
        return '🎬'
      case 'audio':
        return '🎵'
      case 'markdown':
        return '📝'
      case 'image':
        return '🖼️'
      default:
        return '📄'
    }
  }

  return (
    <div
      data-testid="tile-container"
      className={`relative rounded-lg overflow-hidden cursor-pointer transition-all bg-card border-border border ${
        selected ? 'ring-2 ring-primary' : 'hover:shadow-md'
      }`}
      style={{ aspectRatio }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
      onContextMenu={onContextMenu ? (e) => onContextMenu(asset, e) : undefined}
    >
      {/* Main content area */}
      <div className="absolute inset-0">
        {isVideo && isHovered ? (
          <video
            ref={videoRef}
            src={getAssetUrl(asset)}
            className="w-full h-full object-contain bg-black"
            muted={isMuted}
            loop
            playsInline
            autoPlay
            data-testid="video-preview"
          />
        ) : previewUrl ? (
          <img
            src={previewUrl}
            alt={asset.name}
            className="w-full h-full object-contain bg-black"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full bg-muted flex items-center justify-center">
            <span className="text-4xl">{getFileTypeIcon()}</span>
          </div>
        )}
      </div>

      {/* Selection checkbox - visible on hover or when selected */}
      <div
        className={`absolute top-2 left-2 transition-opacity ${
          selected || isHovered ? 'opacity-100' : 'opacity-0'
        }`}
      >
        <input
          type="checkbox"
          checked={selected}
          onChange={handleCheckboxChange}
          className="w-4 h-4 rounded border-input text-primary focus:ring-ring cursor-pointer"
          onClick={(e) => e.stopPropagation()}
        />
      </div>

      {/* Quick actions - visible on hover */}
      <div
        className={`absolute top-2 right-2 flex gap-1 transition-opacity ${
          isHovered ? 'opacity-100' : 'opacity-0'
        }`}
      >
        {isVideo && (
          <button
            onClick={handleVolumeToggle}
            className="p-1.5 rounded-full bg-black/50 hover:bg-black/70 text-white transition-colors"
            title={isMuted ? 'Unmute' : 'Mute'}
          >
            {isMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}
          </button>
        )}
        <button
          onClick={handleMoreClick}
          className="p-1.5 rounded-full bg-black/50 hover:bg-black/70 text-white transition-colors"
          title="More options"
        >
          <MoreHorizontal size={14} />
        </button>
      </div>

      {/* Type indicator badge */}
      <div className="absolute bottom-2 right-2 bg-black/70 text-white text-xs px-2 py-0.5 rounded-full">
        {asset.file_type}
      </div>

      {/* Name footer with gradient overlay */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent p-2 pt-6">
        {isEditing ? (
          <input
            ref={inputRef}
            type="text"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onBlur={handleNameBlur}
            onKeyDown={handleNameKeyDown}
            className="w-full bg-white/90 text-foreground text-sm px-2 py-1 rounded focus:outline-none focus:ring-2 focus:ring-primary"
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <p
            className="text-white text-sm truncate font-medium"
            onDoubleClick={handleNameDoubleClick}
            title={onRename ? 'Double-click to rename' : asset.name}
          >
            {asset.name}
          </p>
        )}
      </div>
    </div>
  )
}
