import { useState, useRef, useEffect } from 'react'
import { Play, Pause, Volume2, VolumeX, Maximize, Download } from 'lucide-react'

interface VideoPlayerProps {
  src: string
  previewSrc?: string
  poster?: string
  autoPlay?: boolean
  loop?: boolean
  muted?: boolean
  showControls?: boolean
  showDownload?: boolean
  className?: string
}

export default function VideoPlayer({
  src,
  previewSrc,
  poster,
  autoPlay = false,
  loop = false,
  muted = false,
  showControls = true,
  showDownload = false,
  className = '',
}: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isPlaying, setIsPlaying] = useState(autoPlay)
  const [isMuted, setIsMuted] = useState(muted)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [isHovering, setIsHovering] = useState(false)
  const [usePreview, setUsePreview] = useState(false)

  const currentSrc = usePreview && previewSrc ? previewSrc : src

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const handleTimeUpdate = () => {
      setCurrentTime(video.currentTime)
      setProgress((video.currentTime / video.duration) * 100)
    }

    const handleLoadedMetadata = () => {
      setDuration(video.duration)
    }

    const handleEnded = () => {
      setIsPlaying(false)
    }

    video.addEventListener('timeupdate', handleTimeUpdate)
    video.addEventListener('loadedmetadata', handleLoadedMetadata)
    video.addEventListener('ended', handleEnded)

    return () => {
      video.removeEventListener('timeupdate', handleTimeUpdate)
      video.removeEventListener('loadedmetadata', handleLoadedMetadata)
      video.removeEventListener('ended', handleEnded)
    }
  }, [currentSrc])

  const togglePlay = () => {
    const video = videoRef.current
    if (!video) return

    if (isPlaying) {
      video.pause()
    } else {
      video.play()
    }
    setIsPlaying(!isPlaying)
  }

  const toggleMute = () => {
    const video = videoRef.current
    if (!video) return

    video.muted = !isMuted
    setIsMuted(!isMuted)
  }

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    const video = videoRef.current
    if (!video) return

    const rect = e.currentTarget.getBoundingClientRect()
    const pos = (e.clientX - rect.left) / rect.width
    video.currentTime = pos * duration
  }

  const handleFullscreen = () => {
    const video = videoRef.current
    if (!video) return

    if (document.fullscreenElement) {
      document.exitFullscreen()
    } else {
      video.requestFullscreen()
    }
  }

  const formatTime = (time: number) => {
    const minutes = Math.floor(time / 60)
    const seconds = Math.floor(time % 60)
    return `${minutes}:${seconds.toString().padStart(2, '0')}`
  }

  const handleDownload = () => {
    const link = document.createElement('a')
    link.href = src
    link.download = src.split('/').pop() || 'video.mp4'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  return (
    <div
      className={`relative bg-black rounded-lg overflow-hidden ${className}`}
      onMouseEnter={() => setIsHovering(true)}
      onMouseLeave={() => setIsHovering(false)}
    >
      <video
        ref={videoRef}
        src={currentSrc}
        poster={poster}
        autoPlay={autoPlay}
        loop={loop}
        muted={isMuted}
        className="w-full h-full object-contain"
        onClick={togglePlay}
      />

      {showControls && (
        <div
          className={`absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-4 transition-opacity ${
            isHovering || !isPlaying ? 'opacity-100' : 'opacity-0'
          }`}
        >
          <div
            className="w-full h-1 bg-gray-600 rounded cursor-pointer mb-3"
            onClick={handleSeek}
          >
            <div
              className="h-full bg-blue-500 rounded"
              style={{ width: `${progress}%` }}
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <button
                onClick={togglePlay}
                className="text-white hover:text-blue-400 transition"
              >
                {isPlaying ? (
                  <Pause className="h-5 w-5" />
                ) : (
                  <Play className="h-5 w-5" />
                )}
              </button>

              <button
                onClick={toggleMute}
                className="text-white hover:text-blue-400 transition"
              >
                {isMuted ? (
                  <VolumeX className="h-5 w-5" />
                ) : (
                  <Volume2 className="h-5 w-5" />
                )}
              </button>

              <span className="text-white text-sm">
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>

            <div className="flex items-center gap-2">
              {previewSrc && (
                <label className="flex items-center gap-1 text-white text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={usePreview}
                    onChange={(e) => setUsePreview(e.target.checked)}
                    className="rounded"
                  />
                  Preview
                </label>
              )}

              {showDownload && (
                <button
                  onClick={handleDownload}
                  className="text-white hover:text-blue-400 transition"
                >
                  <Download className="h-5 w-5" />
                </button>
              )}

              <button
                onClick={handleFullscreen}
                className="text-white hover:text-blue-400 transition"
              >
                <Maximize className="h-5 w-5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {!isPlaying && !showControls && (
        <div
          className="absolute inset-0 flex items-center justify-center bg-black/30 cursor-pointer"
          onClick={togglePlay}
        >
          <Play className="h-16 w-16 text-white" />
        </div>
      )}
    </div>
  )
}
