import { X, Image as ImageIcon, Video, FileText, Music, Tag as TagIcon } from 'lucide-react'
import type { MediaAsset } from '../../api/types/media'
import { getAssetUrl } from '../../api/media'

interface MediaDetailPanelProps {
  asset: MediaAsset | null
  isOpen: boolean
  onClose: () => void
  onTag?: (asset: MediaAsset) => void
}

export function MediaDetailPanel({
  asset,
  isOpen,
  onClose,
  onTag,
}: MediaDetailPanelProps) {
  if (!isOpen || !asset) return null

  const formatFileSize = (bytes: number | null): string => {
    if (!bytes) return 'Unknown'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const getFileTypeIcon = () => {
    switch (asset.file_type) {
      case 'image':
        return <ImageIcon className="w-5 h-5" />
      case 'video':
        return <Video className="w-5 h-5" />
      case 'markdown':
        return <FileText className="w-5 h-5" />
      case 'audio':
        return <Music className="w-5 h-5" />
      default:
        return <FileText className="w-5 h-5" />
    }
  }

  const metadata = asset.asset_metadata as Record<string, unknown> | null
  const width = metadata?.width as number | undefined
  const height = metadata?.height as number | undefined
  const duration = metadata?.duration as number | undefined

  return (
    <div className="w-80 border-l border-border bg-card flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-border flex items-center justify-between">
        <h2 className="font-semibold">Details</h2>
        <button
          onClick={onClose}
          className="p-1 hover:bg-muted rounded"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Preview */}
        <div className="aspect-video bg-muted rounded-lg overflow-hidden">
          {asset.file_type === 'image' ? (
            <img
              src={getAssetUrl(asset)}
              alt={asset.name}
              className="w-full h-full object-cover"
            />
          ) : asset.file_type === 'video' ? (
            <video
              src={getAssetUrl(asset)}
              className="w-full h-full object-cover"
              controls
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-muted-foreground">
              {getFileTypeIcon()}
            </div>
          )}
        </div>

        {/* Name */}
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Name</label>
          <p className="font-medium break-words">{asset.name}</p>
        </div>

        {/* File Type */}
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Type</label>
          <div className="flex items-center gap-2">
            {getFileTypeIcon()}
            <span className="capitalize">{asset.file_type}</span>
          </div>
        </div>

        {/* Size */}
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Size</label>
          <p>{formatFileSize(asset.size_bytes)}</p>
        </div>

        {/* Dimensions */}
        {(width || height) && (
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">Dimensions</label>
            <p>{width} × {height}</p>
          </div>
        )}

        {/* Duration */}
        {duration && (
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">Duration</label>
            <p>{duration.toFixed(2)}s</p>
          </div>
        )}

        {/* Created */}
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Created</label>
          <p className="text-sm">{formatDate(asset.created_at)}</p>
        </div>

        {/* Source */}
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Source</label>
          <p className="capitalize">{asset.source_type}</p>
        </div>

        {/* Tags */}
        <div>
          <label className="text-xs text-muted-foreground mb-2 block">Tags</label>
          <div className="flex flex-wrap gap-1">
            {asset.tags.length > 0 ? (
              asset.tags.map((tag) => (
                <span
                  key={tag.id}
                  className="text-xs px-2 py-1 rounded-full"
                  style={{
                    backgroundColor: tag.color,
                    color: '#ffffff',
                  }}
                >
                  {tag.name}
                </span>
              ))
            ) : (
              <span className="text-sm text-muted-foreground">No tags</span>
            )}
          </div>
          {onTag && (
            <button
              onClick={() => onTag(asset)}
              className="mt-2 text-xs text-primary hover:underline flex items-center gap-1"
            >
              <TagIcon className="w-3 h-3" />
              Add tags
            </button>
          )}
        </div>

        {/* Metadata JSON */}
        {metadata && Object.keys(metadata).length > 0 && (
          <div>
            <label className="text-xs text-muted-foreground mb-1 block">Metadata</label>
            <pre className="text-xs bg-muted p-2 rounded overflow-auto max-h-40">
              {JSON.stringify(metadata, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
