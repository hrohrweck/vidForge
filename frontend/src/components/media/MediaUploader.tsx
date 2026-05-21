import { useCallback, useState } from 'react'
import { Upload, X } from 'lucide-react'
import { useUploadAssets } from '../../hooks/useMedia'

interface MediaUploaderProps {
  folderId?: string
  onUploadComplete?: () => void
}

export function MediaUploader({ folderId, onUploadComplete }: MediaUploaderProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<Map<string, number>>(new Map())
  const uploadAssets = useUploadAssets()

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)

      const files = Array.from(e.dataTransfer.files)
      if (files.length === 0) return

      uploadAssets.mutate(
        {
          files,
          folderId,
          onProgress: (progress) => {
            setUploadProgress((prev) => {
              const next = new Map(prev)
              next.set('total', progress.percentage)
              return next
            })
          },
        },
        {
          onSuccess: () => {
            setUploadProgress(new Map())
            onUploadComplete?.()
          },
        }
      )
    },
    [folderId, uploadAssets, onUploadComplete]
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || [])
      if (files.length === 0) return

      uploadAssets.mutate(
        {
          files,
          folderId,
        },
        {
          onSuccess: () => {
            onUploadComplete?.()
          },
        }
      )
    },
    [folderId, uploadAssets, onUploadComplete]
  )

  return (
    <div className="space-y-2">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
          isDragging
            ? 'border-primary bg-primary/10'
            : 'border-border hover:border-muted-foreground'
        }`}
      >
        <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
        <p className="text-sm text-muted-foreground mb-1">
          Drag and drop files here, or{' '}
          <label className="text-primary hover:text-primary/80 cursor-pointer">
            browse
            <input
              type="file"
              multiple
              className="hidden"
              onChange={handleFileSelect}
            />
          </label>
        </p>
        <p className="text-xs text-muted-foreground">
          Supports images, videos, audio, and markdown files
        </p>
      </div>

      {uploadAssets.isPending && (
        <div className="bg-primary/10 border border-primary/20 rounded-lg p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-primary">Uploading...</span>
            <X
              className="h-4 w-4 text-primary cursor-pointer"
              onClick={() => uploadAssets.reset()}
            />
          </div>
          <div className="w-full bg-muted rounded-full h-2">
            <div
              className="bg-primary h-2 rounded-full transition-all"
              style={{
                width: `${uploadProgress.get('total') || 0}%`,
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
