import { useState, useCallback } from 'react'
import { Search, Upload, Folder, ChevronRight, X, Check, Image as ImageIcon } from 'lucide-react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { useAssets, useFolderTree, useUploadAssets } from '../../hooks/useMedia'
import type { MediaAsset } from '../../api/types/media'

interface AssetPickerModalProps {
  isOpen: boolean
  onClose: () => void
  onSelect: (asset: MediaAsset) => void
}

export function AssetPickerModal({ isOpen, onClose, onSelect }: AssetPickerModalProps) {
  const [selectedFolderId, setSelectedFolderId] = useState<string | undefined>()
  const [search, setSearch] = useState('')
  const [selectedAsset, setSelectedAsset] = useState<MediaAsset | null>(null)
  const [isUploading, setIsUploading] = useState(false)

  // Fetch folders and assets
  const { data: folderTree = [] } = useFolderTree()
  const { data, isLoading } = useAssets({
    folder_id: selectedFolderId,
    search: search || undefined,
    file_type: 'image',
    limit: 50,
  })
  const uploadMutation = useUploadAssets()

  const allAssets = data?.pages?.flatMap((p: { assets: MediaAsset[] }) => p.assets) ?? []

  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    setIsUploading(true)
    try {
      await uploadMutation.mutateAsync({ files: Array.from(files), folderId: selectedFolderId })
    } finally {
      setIsUploading(false)
      e.target.value = ''
    }
  }, [uploadMutation, selectedFolderId])

  const handleSelect = () => {
    if (selectedAsset) {
      onSelect(selectedAsset)
      onClose()
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50">
      <div className="bg-background rounded-lg shadow-xl w-full max-w-4xl max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">Choose Reference Image</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 flex min-h-0">
          {/* Left sidebar — folder navigation */}
          <div className="w-56 shrink-0 border-r overflow-y-auto p-2">
            <div className="text-xs font-semibold text-muted-foreground px-2 pb-1">Folders</div>
            <button
              onClick={() => setSelectedFolderId(undefined)}
              className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-sm text-left ${!selectedFolderId ? 'bg-primary/10 text-primary' : 'hover:bg-muted'}`}
            >
              <Folder className="h-4 w-4 shrink-0" />
              <span className="truncate">All Assets</span>
            </button>
            {folderTree.map((f) => (
              <button
                key={f.id}
                onClick={() => setSelectedFolderId(f.id)}
                className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-sm text-left ${selectedFolderId === f.id ? 'bg-primary/10 text-primary' : 'hover:bg-muted'}`}
              >
                <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
                <span className="truncate">{f.name}</span>
              </button>
            ))}
          </div>

          {/* Right content area */}
          <div className="flex-1 flex flex-col min-w-0">
            {/* Search & Upload bar */}
            <div className="flex items-center gap-2 p-3 border-b">
              <div className="relative flex-1">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  className="pl-8"
                  placeholder="Search images..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <label className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md border text-sm cursor-pointer hover:bg-muted">
                <Upload className="h-4 w-4" />
                {isUploading ? 'Uploading...' : 'Upload'}
                <input type="file" accept="image/*" className="hidden" onChange={handleUpload} disabled={isUploading} />
              </label>
            </div>

            {/* Image grid */}
            <div className="flex-1 overflow-y-auto p-3">
              {isLoading ? (
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                  Loading...
                </div>
              ) : allAssets.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-sm text-muted-foreground gap-2">
                  <ImageIcon className="h-8 w-8 opacity-40" />
                  <p>No images found</p>
                </div>
              ) : (
                <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-3">
                  {allAssets.map((asset) => {
                    const selected = selectedAsset?.id === asset.id
                    return (
                      <button
                        key={asset.id}
                        onClick={() => setSelectedAsset(selected ? null : asset)}
                        className={`relative rounded-lg border overflow-hidden aspect-square group ${
                          selected ? 'ring-2 ring-primary ring-offset-2' : 'hover:ring-1 hover:ring-border'
                        }`}
                      >
                        {asset.file_type === 'image' ? (
                          <img
                            src={`/api/uploads/stream/${asset.preview_path || asset.file_path}`}
                            alt={asset.name}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center bg-muted">
                            <ImageIcon className="h-8 w-8 text-muted-foreground/40" />
                          </div>
                        )}
                        {selected && (
                          <div className="absolute top-2 right-2 bg-primary rounded-full p-0.5">
                            <Check className="h-3.5 w-3.5 text-primary-foreground" />
                          </div>
                        )}
                        <div className="absolute bottom-0 left-0 right-0 bg-black/60 px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <p className="text-xs text-white truncate">{asset.name}</p>
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer with OK/Cancel */}
        <div className="flex items-center justify-between p-4 border-t">
          <p className="text-sm text-muted-foreground">
            {selectedAsset ? `Selected: ${selectedAsset.name}` : 'No image selected'}
          </p>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button onClick={handleSelect} disabled={!selectedAsset}>
              OK
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
