import { useState } from 'react'
import { X } from 'lucide-react'
import { MediaGrid } from './MediaGrid'
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
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">Select Asset</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-muted rounded"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          <MediaGrid
            query={{ file_type: fileType, limit: 50 }}
            onAssetClick={(asset) => setSelectedAsset(asset)}
          />
        </div>

        {/* Footer */}
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
