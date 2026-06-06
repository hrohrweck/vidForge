import { useEffect, useCallback, useState } from 'react'
import { X, ChevronLeft, ChevronRight, Volume2, VolumeX } from 'lucide-react'
import type { MediaAsset } from '../../api/types/media'
import { getAssetUrl } from '../../api/media'

interface LightboxProps {
  assets: MediaAsset[]
  currentIndex: number
  isOpen: boolean
  onClose: () => void
  onNavigate?: (index: number) => void
}

export function Lightbox({
  assets,
  currentIndex,
  isOpen,
  onClose,
  onNavigate,
}: LightboxProps) {
  const [isMuted, setIsMuted] = useState(true)

  const currentAsset = assets[currentIndex]

  const goToPrevious = useCallback(() => {
    if (currentIndex > 0 && onNavigate) {
      onNavigate(currentIndex - 1)
    }
  }, [currentIndex, onNavigate])

  const goToNext = useCallback(() => {
    if (currentIndex < assets.length - 1 && onNavigate) {
      onNavigate(currentIndex + 1)
    }
  }, [currentIndex, assets.length, onNavigate])

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      } else if (e.key === 'ArrowLeft') {
        goToPrevious()
      } else if (e.key === 'ArrowRight') {
        goToNext()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose, goToPrevious, goToNext])

  if (!isOpen || !currentAsset) return null

  const isVideo = currentAsset.file_type === 'video'
  const mediaUrl = getAssetUrl(currentAsset)

  return (
    <div className="fixed inset-0 z-50 bg-black/95 flex items-center justify-center">
      {/* Close button */}
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white"
      >
        <X className="w-6 h-6" />
      </button>

      {/* Navigation - Previous */}
      {currentIndex > 0 && (
        <button
          onClick={goToPrevious}
          className="absolute left-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white"
        >
          <ChevronLeft className="w-8 h-8" />
        </button>
      )}

      {/* Navigation - Next */}
      {currentIndex < assets.length - 1 && (
        <button
          onClick={goToNext}
          className="absolute right-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white"
        >
          <ChevronRight className="w-8 h-8" />
        </button>
      )}

      {/* Media content */}
      <div className="max-w-full max-h-full p-8">
        {isVideo ? (
          <div className="relative">
            <video
              src={mediaUrl}
              className="max-w-full max-h-[85vh] rounded-lg"
              autoPlay
              muted={isMuted}
              controls
              loop
            />
            <button
              onClick={() => setIsMuted(!isMuted)}
              className="absolute bottom-4 right-4 p-2 rounded-full bg-black/50 hover:bg-black/70 text-white"
            >
              {isMuted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
            </button>
          </div>
        ) : (
          <img
            src={mediaUrl}
            alt={currentAsset.name}
            className="max-w-full max-h-[85vh] object-contain rounded-lg"
          />
        )}
      </div>

      {/* Info bar */}
      <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-black/80 to-transparent">
        <div className="flex items-center justify-between text-white">
          <p className="text-sm font-medium">{currentAsset.name}</p>
          <p className="text-xs text-white/70">
            {currentIndex + 1} / {assets.length}
          </p>
        </div>
      </div>
    </div>
  )
}
