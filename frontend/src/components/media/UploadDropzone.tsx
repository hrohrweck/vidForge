import { useCallback, useState, useRef } from 'react'
import { UploadCloud, X } from 'lucide-react'

interface UploadDropzoneProps {
  isOpen: boolean
  onClose: () => void
  onFilesSelected: (files: File[]) => void
}

export function UploadDropzone({
  isOpen,
  onClose,
  onFilesSelected,
}: UploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFiles = useCallback((files: FileList | null) => {
    if (files && files.length > 0) {
      const fileArray = Array.from(files)
      onFilesSelected(fileArray)
      onClose()
    }
  }, [onFilesSelected, onClose])

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    handleFiles(e.dataTransfer.files)
  }, [handleFiles])

  const handleClick = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files)
  }, [handleFiles])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center">
      <div
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={handleClick}
        className={`
          w-full max-w-2xl mx-4 p-12
          border-2 border-dashed rounded-lg
          bg-card
          transition-all duration-200
          cursor-pointer
          ${
            isDragging
              ? 'border-primary bg-primary/5 scale-105'
              : 'border-border hover:border-primary/50'
          }
        `}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*,video/*,audio/*,.md"
          onChange={handleFileInputChange}
          className="hidden"
        />
        
        <div className="flex flex-col items-center gap-4 text-center">
          <UploadCloud
            className={`w-16 h-16 ${
              isDragging ? 'text-primary' : 'text-muted-foreground'
            }`}
          />
          
          <div>
            <p className="text-lg font-medium mb-2">
              {isDragging ? 'Drop files here' : 'Drag & drop files here'}
            </p>
            <p className="text-sm text-muted-foreground">
              or click to select files
            </p>
          </div>

          <div className="flex flex-wrap gap-2 justify-center mt-4">
            <span className="text-xs px-2 py-1 bg-muted rounded text-muted-foreground">
              Images
            </span>
            <span className="text-xs px-2 py-1 bg-muted rounded text-muted-foreground">
              Videos
            </span>
            <span className="text-xs px-2 py-1 bg-muted rounded text-muted-foreground">
              Audio
            </span>
            <span className="text-xs px-2 py-1 bg-muted rounded text-muted-foreground">
              Markdown
            </span>
          </div>
        </div>
      </div>

      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2 rounded-full bg-muted hover:bg-muted/80"
      >
        <X className="w-5 h-5" />
      </button>
    </div>
  )
}
