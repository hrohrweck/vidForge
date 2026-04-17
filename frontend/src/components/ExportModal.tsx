import { useState } from 'react'
import { X, Download, Upload, Music } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { scenesApi, ExportRequest, ExportOptions } from '../api/client'

interface ExportModalProps {
  jobId: string
  exportOptions: ExportOptions | undefined
  onClose: () => void
  onExported: () => void
}

export function ExportModal({ jobId, exportOptions, onClose, onExported }: ExportModalProps) {
  const [audioVolume, setAudioVolume] = useState(
    exportOptions?.default_options.audio_volume ?? 1.0
  )
  const [backgroundMusic, setBackgroundMusic] = useState<File | null>(null)
  const [backgroundMusicVolume, setBackgroundMusicVolume] = useState(
    exportOptions?.default_options.background_music_volume ?? 0.3
  )
  const [transitionType, setTransitionType] = useState(
    exportOptions?.default_options.transition_type ?? 'cut'
  )
  const [isExporting, setIsExporting] = useState(false)
  const [backgroundMusicPath, setBackgroundMusicPath] = useState<string | null>(null)

  const handleBackgroundMusicUpload = async () => {
    if (!backgroundMusic) return

    const formData = new FormData()
    formData.append('file', backgroundMusic)

    try {
      const response = await fetch('/api/uploads/audio', {
        method: 'POST',
        body: formData,
        headers: {
          Authorization: `Bearer ${localStorage.getItem('token')}`,
        },
      })

      if (!response.ok) throw new Error('Upload failed')

      const data = await response.json()
      setBackgroundMusicPath(data.path)
    } catch (error) {
      console.error('Failed to upload background music:', error)
    }
  }

  const handleExport = async () => {
    setIsExporting(true)

    try {
      const request: ExportRequest = {
        audio_file: exportOptions?.audio_file || undefined,
        background_music: backgroundMusicPath || undefined,
        audio_volume: audioVolume,
        background_music_volume: backgroundMusicVolume,
        transition_type: transitionType,
      }

      await scenesApi.export(jobId, request)
      onExported()
    } catch (error) {
      console.error('Failed to start export:', error)
      setIsExporting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-background rounded-lg shadow-lg w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Download className="h-5 w-5" />
            Export Video
          </h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="p-4 space-y-6">
          <div className="space-y-4">
            <h3 className="font-medium flex items-center gap-2">
              <Music className="h-4 w-4" />
              Audio Settings
            </h3>

            <div className="space-y-2">
              <Label>Original Audio Volume</Label>
              <div className="flex items-center gap-4">
                <Input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={audioVolume}
                  onChange={(e) => setAudioVolume(Number(e.target.value))}
                  className="flex-grow"
                />
                <span className="text-sm text-muted-foreground w-12 text-right">
                  {(audioVolume * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          </div>

          <div className="border-t pt-4 space-y-4">
            <h3 className="font-medium flex items-center gap-2">
              <Music className="h-4 w-4" />
              Background Music (Optional)
            </h3>

            <div className="space-y-2">
              <Label>Background Music File</Label>
              <div className="flex items-center gap-2">
                <Input
                  type="file"
                  accept=".mp3,.wav,.ogg,.flac"
                  onChange={(e) => setBackgroundMusic(e.target.files?.[0] || null)}
                  className="flex-grow"
                />
                {backgroundMusic && !backgroundMusicPath && (
                  <Button size="sm" onClick={handleBackgroundMusicUpload}>
                    <Upload className="h-4 w-4" />
                  </Button>
                )}
              </div>
              {backgroundMusicPath && (
                <p className="text-xs text-green-600 flex items-center gap-1">
                  <Download className="h-3 w-3" />
                  {backgroundMusic.name} uploaded
                </p>
              )}
            </div>

            {backgroundMusicPath && (
              <div className="space-y-2">
                <Label>Background Music Volume</Label>
                <div className="flex items-center gap-4">
                  <Input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={backgroundMusicVolume}
                    onChange={(e) => setBackgroundMusicVolume(Number(e.target.value))}
                    className="flex-grow"
                  />
                  <span className="text-sm text-muted-foreground w-12 text-right">
                    {(backgroundMusicVolume * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            )}
          </div>

          <div className="border-t pt-4 space-y-4">
            <h3 className="font-medium">Scene Transitions</h3>

            <div className="space-y-2">
              <Label>Transition Type</Label>
              <div className="grid grid-cols-3 gap-2">
                {(exportOptions?.transition_types || ['cut', 'crossfade', 'dissolve']).map((type) => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setTransitionType(type)}
                    className={`px-4 py-2 rounded-md border text-sm font-medium transition-colors ${
                      transitionType === type
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'bg-background hover:bg-muted'
                    }`}
                  >
                    {type.charAt(0).toUpperCase() + type.slice(1)}
                  </button>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                {transitionType === 'cut' && 'Instant transition between scenes'}
                {transitionType === 'crossfade' && 'Smooth fade between scenes'}
                {transitionType === 'dissolve' && 'Gradual blend between scenes'}
              </p>
            </div>
          </div>

          {exportOptions && (
            <div className="bg-muted rounded-lg p-3 text-sm">
              <div className="flex justify-between text-muted-foreground">
                <span>Scenes:</span>
                <span>{exportOptions.completed_scenes} / {exportOptions.total_scenes}</span>
              </div>
              <div className="flex justify-between text-muted-foreground mt-1">
                <span>Can Export:</span>
                <span className={exportOptions.can_export ? 'text-green-600' : 'text-yellow-600'}>
                  {exportOptions.can_export ? 'Yes' : 'No (waiting for videos)'}
                </span>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 p-4 border-t">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleExport}
            disabled={isExporting || (backgroundMusic !== null && !backgroundMusicPath)}
          >
            {isExporting ? (
              <>
                <span className="animate-spin mr-2">⏳</span>
                Exporting...
              </>
            ) : (
              <>
                <Download className="h-4 w-4 mr-2" />
                Start Export
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
