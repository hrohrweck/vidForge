import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAsset, useUpdateAsset } from '../hooks/useMedia'
import { getAssetUrl } from '../api/media'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function AssetDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: asset, isLoading, error } = useAsset(id || '')
  const updateAsset = useUpdateAsset()
  const [isEditing, setIsEditing] = useState(false)
  const [editName, setEditName] = useState('')

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  if (error || !asset) {
    return (
      <div className="flex items-center justify-center h-screen text-destructive">
        Error loading asset: {error?.message || 'Not found'}
      </div>
    )
  }

  const handleNameSave = () => {
    if (editName && editName !== asset.name) {
      updateAsset.mutate({ id: asset.id, payload: { name: editName } })
    }
    setIsEditing(false)
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      {/* Header */}
      <div className="mb-6">
        <button
          onClick={() => navigate('/media')}
          className="text-primary hover:text-primary/80 mb-4"
        >
          ← Back to Library
        </button>

        {isEditing ? (
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              className="text-2xl font-bold border-b-2 border-primary focus:outline-none"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleNameSave()
                if (e.key === 'Escape') setIsEditing(false)
              }}
            />
            <button
              onClick={handleNameSave}
              className="px-3 py-1 bg-primary text-primary-foreground rounded hover:bg-primary/90"
            >
              Save
            </button>
          </div>
        ) : (
          <h1
            className="text-2xl font-bold cursor-pointer hover:text-primary"
            onClick={() => {
              setEditName(asset.name)
              setIsEditing(true)
            }}
          >
            {asset.name}
          </h1>
        )}
      </div>

      {/* Asset Preview */}
      <div className="mb-6">
        {asset.file_type === 'video' ? (
          <video
            src={getAssetUrl(asset.file_path)}
            controls
            className="w-full max-h-96 rounded-lg"
          />
        ) : asset.file_type === 'image' ? (
          <img
            src={getAssetUrl(asset.file_path)}
            alt={asset.name}
            className="w-full max-h-96 object-contain rounded-lg"
          />
        ) : asset.file_type === 'markdown' ? (
          <div className="border border-border rounded-lg p-4 bg-background">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {(asset.asset_metadata?.content as string) || '# Empty markdown'}
            </ReactMarkdown>
          </div>
        ) : (
          <div className="flex items-center justify-center h-64 bg-muted rounded-lg">
            <span className="text-6xl">
              {asset.file_type === 'audio' && '🎵'}
            </span>
          </div>
        )}
      </div>

      {/* Asset Details */}
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-muted-foreground">Type:</span>{' '}
          <span className="capitalize">{asset.file_type}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Size:</span>{' '}
          <span>{asset.size_bytes ? `${(asset.size_bytes / 1024 / 1024).toFixed(2)} MB` : 'Unknown'}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Source:</span>{' '}
          <span className="capitalize">{asset.source_type}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Created:</span>{' '}
          <span>{new Date(asset.created_at).toLocaleDateString()}</span>
        </div>
        {asset.mime_type && (
          <div>
            <span className="text-muted-foreground">MIME Type:</span>{' '}
            <span>{asset.mime_type}</span>
          </div>
        )}
        {asset.tags.length > 0 && (
          <div className="col-span-2">
            <span className="text-muted-foreground">Tags:</span>{' '}
            <div className="inline-flex gap-2 mt-1">
              {asset.tags.map((tag) => (
                <span
                  key={tag.id}
                  className="px-2 py-1 rounded-full text-xs"
                  style={{ backgroundColor: `#${tag.color}`, color: '#fff' }}
                >
                  {tag.name}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
