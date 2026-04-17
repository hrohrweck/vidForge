import { useState } from 'react'
import { X, Upload, Save } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import type { VideoScene } from '../api/client'

interface SceneEditModalProps {
  scene: VideoScene
  onClose: () => void
  onSave: (updates: Partial<VideoScene>) => void
}

export function SceneEditModal({ scene, onClose, onSave }: SceneEditModalProps) {
  const [imagePrompt, setImagePrompt] = useState(scene.image_prompt || '')
  const [visualDescription, setVisualDescription] = useState(scene.visual_description || '')
  const [lyricsSegment, setLyricsSegment] = useState(scene.lyrics_segment || '')
  const [mood, setMood] = useState(scene.mood)
  const [cameraMovement, setCameraMovement] = useState(scene.camera_movement)
  const [startTime, setStartTime] = useState(scene.start_time)
  const [endTime, setEndTime] = useState(scene.end_time)
  const [referenceImage, setReferenceImage] = useState<File | null>(null)

  const handleSave = () => {
    onSave({
      image_prompt: imagePrompt,
      visual_description: visualDescription,
      lyrics_segment: lyricsSegment,
      mood,
      camera_movement: cameraMovement,
      start_time: startTime,
      end_time: endTime,
    })
  }

  const handleImageUpload = async () => {
    if (!referenceImage) return

    const formData = new FormData()
    formData.append('file', referenceImage)

    try {
      const response = await fetch('/api/uploads/image', {
        method: 'POST',
        body: formData,
        headers: {
          Authorization: `Bearer ${localStorage.getItem('token')}`,
        },
      })

      if (!response.ok) throw new Error('Upload failed')

      const data = await response.json()
      onSave({
        reference_image_path: data.path,
      })
    } catch (error) {
      console.error('Failed to upload image:', error)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-background rounded-lg shadow-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">Edit Scene {scene.scene_number}</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="p-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Start Time (seconds)</Label>
              <Input
                type="number"
                step="0.1"
                value={startTime}
                onChange={(e) => setStartTime(Number(e.target.value))}
              />
            </div>
            <div className="space-y-2">
              <Label>End Time (seconds)</Label>
              <Input
                type="number"
                step="0.1"
                value={endTime}
                onChange={(e) => setEndTime(Number(e.target.value))}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Image Generation Prompt</Label>
            <textarea
              className="w-full h-20 rounded-md border border-input bg-background px-3 py-2"
              value={imagePrompt}
              onChange={(e) => setImagePrompt(e.target.value)}
              placeholder="Prompt for generating the first frame image..."
            />
          </div>

          <div className="space-y-2">
            <Label>Visual Description</Label>
            <textarea
              className="w-full h-20 rounded-md border border-input bg-background px-3 py-2"
              value={visualDescription}
              onChange={(e) => setVisualDescription(e.target.value)}
              placeholder="Detailed description of what should appear in this scene..."
            />
          </div>

          <div className="space-y-2">
            <Label>Lyrics Segment</Label>
            <textarea
              className="w-full h-16 rounded-md border border-input bg-background px-3 py-2"
              value={lyricsSegment}
              onChange={(e) => setLyricsSegment(e.target.value)}
              placeholder="Lyrics for this scene..."
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Mood</Label>
              <select
                className="w-full h-10 rounded-md border border-input bg-background px-3 py-2"
                value={mood}
                onChange={(e) => setMood(e.target.value)}
              >
                <option value="neutral">Neutral</option>
                <option value="energetic">Energetic</option>
                <option value="calm">Calm</option>
                <option value="melancholic">Melancholic</option>
                <option value="happy">Happy</option>
                <option value="mysterious">Mysterious</option>
                <option value="dramatic">Dramatic</option>
                <option value="romantic">Romantic</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label>Camera Movement</Label>
              <select
                className="w-full h-10 rounded-md border border-input bg-background px-3 py-2"
                value={cameraMovement}
                onChange={(e) => setCameraMovement(e.target.value)}
              >
                <option value="static">Static</option>
                <option value="pan_left">Pan Left</option>
                <option value="pan_right">Pan Right</option>
                <option value="zoom_in">Zoom In</option>
                <option value="zoom_out">Zoom Out</option>
                <option value="dolly">Dolly</option>
                <option value="tilt_up">Tilt Up</option>
                <option value="tilt_down">Tilt Down</option>
                <option value="orbit">Orbit</option>
              </select>
            </div>
          </div>

          <div className="space-y-2">
            <Label>Reference Image (Optional)</Label>
            <div className="flex gap-2">
              <Input
                type="file"
                accept="image/*"
                onChange={(e) => setReferenceImage(e.target.files?.[0] || null)}
                className="flex-1"
              />
              {referenceImage && (
                <Button onClick={handleImageUpload} variant="outline">
                  <Upload className="h-4 w-4 mr-2" />
                  Upload
                </Button>
              )}
            </div>
            {scene.reference_image_path && (
              <div className="mt-2">
                <p className="text-sm text-muted-foreground mb-1">Current reference:</p>
                <img
                  src={`/api/uploads/${scene.reference_image_path}`}
                  alt="Reference"
                  className="w-32 h-32 object-cover rounded"
                />
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 p-4 border-t">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave}>
            <Save className="h-4 w-4 mr-2" />
            Save Changes
          </Button>
        </div>
      </div>
    </div>
  )
}
