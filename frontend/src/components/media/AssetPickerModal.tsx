import { useState } from 'react'
import { X } from 'lucide-react'
import { useAssets } from '../../hooks/useMedia'
import { MediaTile } from './MediaTile'
import type { MediaAsset } from '../../api/types/media'

interface AssetPickerModalProps {
  isOpen: boolean
  onClose: () => void
  onSelect: (asset: MediaAsset) => void
  fileType?: 'image' | 'video' | 'audio' | 'markdown'
}

export function AssetPickerModal({
  isOpen,
  onClose,
  onSelect,
  fileType,
}: AssetPickerModalProps) {
  const [selectedAsset, setSelectedAsset] = useState<MediaAsset | null>(null)
  const { data, isLoading } = useAssets({ file_type: fileType, limit: 50 })

  if (!isOpen) return null

  const handleSelect = () => {
    if (selectedAsset) {
      onSelect(selectedAsset)
      onClose()
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-background rounded-lg shadow-xl w-full max-w-4xl max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">Select Asset</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-muted rounded"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
              {Array.from({ length: 12 }).map((_, i) => (
                <div key={i} className="bg-card rounded-lg border border-border overflow-hidden animate-pulse">
                  <div className="aspect-video bg-muted" />
                  <div className="p-3 space-y-2">
                    <div className="h-4 bg-muted rounded w-3/4" />
                    <div className="h-3 bg-muted rounded w-1/2" />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
              {data?.pages.flatMap((page) => page.assets).map((asset) => (
                <MediaTile
                  key={asset.id}
                  asset={asset}
                  selected={selectedAsset?.id === asset.id}
                  onSelect={() => setSelectedAsset(asset)}
                />
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 p-4 border-t">
          <button
            onClick={onClose}
            className="px-4 py-2 text-muted-foreground hover:bg-muted rounded"
          >
            Cancel
          </button>
          <button
            onClick={handleSelect}
            disabled={!selectedAsset}
            className="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
          >
            Select
          </button>
        </div>
      </div>
    </div>
  )
}