import { Pencil, Upload, Play, Clock } from 'lucide-react'
import { Button } from '../components/ui/button'

interface Scene {
  id: string
  scene_number: number
  start_time: number
  end_time: number
  lyrics_segment: string | null
  visual_description: string | null
  image_prompt: string | null
  mood: string
  camera_movement: string
  reference_image_path: string | null
  thumbnail_path: string | null
  generated_video_path: string | null
  status: string
}

interface SceneCardProps {
  scene: Scene
  index: number
  onEdit: () => void
  formatTime: (seconds: number) => string
}

export function SceneCard({ scene, index, onEdit, formatTime }: SceneCardProps) {
  const duration = scene.end_time - scene.start_time

  return (
    <div className="flex-shrink-0 w-48 bg-secondary rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">
          Scene {scene.scene_number}
        </span>
        <Button variant="ghost" size="sm" onClick={onEdit} className="h-6 w-6 p-0">
          <Pencil className="h-3 w-3" />
        </Button>
      </div>

      <div className="relative aspect-video bg-muted rounded overflow-hidden">
        {scene.thumbnail_path ? (
          <img
            src={`/api/uploads/${scene.thumbnail_path}`}
            alt={`Scene ${scene.scene_number}`}
            className="w-full h-full object-cover"
          />
        ) : scene.reference_image_path ? (
          <img
            src={`/api/uploads/${scene.reference_image_path}`}
            alt={`Scene ${scene.scene_number} reference`}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <span className="text-xs text-muted-foreground">No preview</span>
          </div>
        )}
        
        {scene.generated_video_path && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50">
            <Play className="h-8 w-8 text-white" />
          </div>
        )}
      </div>

      <div className="space-y-1">
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          <span>
            {formatTime(scene.start_time)} - {formatTime(scene.end_time)}
          </span>
          <span className="ml-auto">({duration.toFixed(1)}s)</span>
        </div>

        {scene.image_prompt && (
          <p className="text-xs line-clamp-2">{scene.image_prompt}</p>
        )}

        {scene.lyrics_segment && (
          <p className="text-xs text-muted-foreground italic line-clamp-2">
            "{scene.lyrics_segment}"
          </p>
        )}
      </div>

      <div className="flex items-center gap-1">
        <span className="text-xs px-1.5 py-0.5 bg-primary/10 rounded">{scene.mood}</span>
        <span className="text-xs px-1.5 py-0.5 bg-secondary rounded">{scene.camera_movement}</span>
      </div>
    </div>
  )
}
