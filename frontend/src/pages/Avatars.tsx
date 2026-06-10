import { useState, useCallback, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Upload,
  User,
  Loader2,
  FolderOpen,
  Trash2,
  Star,
  ImagePlus,
  Wand2,
  Cpu,
  Box,
  Tag,
  ImageOff,
  Check,
} from 'lucide-react'
import {
  avatarsApi,
  type CreateAvatarRequest,
  type UpdateAvatarRequest,
  type AvatarGender,
  type ConsistencyStrategy,
  type Avatar as AvatarType,
  type AvatarImage,
} from '../api/avatars'
import { objectsApi, type ObjectRef, type CreateObjectRefRequest } from '../api/objects'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Textarea } from '../components/ui/textarea'
import { Badge } from '../components/ui/badge'
import { Card, CardContent } from '../components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '../components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select'
import { AssetPickerModal } from '../components/media/AssetPickerModal'
import { DeleteConfirmationModal } from '../components/DeleteConfirmationModal'
import type { MediaAsset } from '../api/types/media'
import { toast } from '../hooks/use-toast'

// ─── Display label helpers ───────────────────────────────────────────

const GENDER_LABELS: Record<AvatarGender, string> = {
  Male: 'Male',
  Female: 'Female',
  'Non-binary': 'Non-binary',
  Other: 'Other',
}

const STRATEGY_LABELS: Record<ConsistencyStrategy, string> = {
  ip_adapter: 'IP-Adapter/InstantID',
  face_swap: 'Face-swap',
  lora: 'LoRA',
  prompt_only: 'Prompt-only',
}

const GENDER_BADGE_VARIANTS: Record<AvatarGender, 'default' | 'secondary' | 'outline'> = {
  Male: 'default',
  Female: 'secondary',
  'Non-binary': 'outline',
  Other: 'outline',
}

const STRATEGY_BADGE_VARIANTS: Record<ConsistencyStrategy, 'default' | 'secondary' | 'outline'> = {
  ip_adapter: 'default',
  face_swap: 'secondary',
  lora: 'outline',
  prompt_only: 'outline',
}

const LORA_STATUS_LABELS: Record<string, string> = {
  not_trained: 'Not Trained',
  training: 'Training…',
  trained: 'Trained',
  failed: 'Failed',
}

const LORA_STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  not_trained: 'outline',
  training: 'secondary',
  trained: 'default',
  failed: 'destructive',
}

// ─── Streaming URL helper ────────────────────────────────────────────

function getImageUrl(
  image: { thumbnailUrl?: string; storagePath: string },
  avatarId?: string
): string {
  if (image.thumbnailUrl) return image.thumbnailUrl
  if (avatarId) {
    const filename = image.storagePath.split('/').pop()
    return `/api/avatars/${avatarId}/stream/${filename}`
  }
  return `/api/uploads/stream/${image.storagePath}`
}

// ─── Selected file tracking ──────────────────────────────────────────

interface SelectedFile {
  /** The native File from a direct upload */
  file?: File
  /** MediaAsset from the AssetPickerModal */
  asset?: MediaAsset
  /** Object URL for preview */
  previewUrl: string
}

// ─── Avatar Card ─────────────────────────────────────────────────────

function AvatarCard({
  avatar,
  onClick,
}: {
  avatar: AvatarType
  onClick: (avatar: AvatarType) => void
}) {
  const primaryImage = avatar.images?.find((img) => img.isPrimary)

  return (
    <Card
      className="group overflow-hidden transition-shadow hover:shadow-md cursor-pointer"
      onClick={() => onClick(avatar)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onClick(avatar)
      }}
    >
      {/* Thumbnail */}
      <div className="aspect-square bg-muted relative overflow-hidden">
        {primaryImage?.storagePath ? (
          <img
            src={getImageUrl(primaryImage, avatar.id)}
            alt={avatar.name}
            className="h-full w-full object-cover transition-transform group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-muted-foreground">
            <User className="h-12 w-12" />
          </div>
        )}
        {/* Image count badge */}
        {avatar.images?.length > 0 && (
          <span className="absolute bottom-2 right-2 rounded-full bg-background/90 px-2 py-0.5 text-xs font-medium shadow">
            {avatar.images.length} image{avatar.images.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      <CardContent className="space-y-3 p-4">
        {/* Name */}
        <div>
          <h3 className="truncate font-semibold leading-tight">{avatar.name}</h3>
        </div>

        {/* Badges */}
        <div className="flex flex-wrap gap-1.5">
          <Badge variant={GENDER_BADGE_VARIANTS[avatar.gender]}>
            {GENDER_LABELS[avatar.gender]}
          </Badge>
          <Badge variant={STRATEGY_BADGE_VARIANTS[avatar.consistencyStrategy]}>
            {STRATEGY_LABELS[avatar.consistencyStrategy]}
          </Badge>
          {avatar.consistencyStrategy === 'lora' && (
            <Badge variant={LORA_STATUS_VARIANTS[avatar.loraTrainingStatus] || 'outline'}>
              {LORA_STATUS_LABELS[avatar.loraTrainingStatus] || avatar.loraTrainingStatus}
            </Badge>
          )}
        </div>

        {/* Bio snippet */}
        {avatar.bio && (
          <p className="line-clamp-2 text-xs text-muted-foreground leading-relaxed">
            {avatar.bio}
          </p>
        )}

        {/* Job count */}
        {avatar.jobCount > 0 && (
          <p className="text-xs text-muted-foreground">
            Used in {avatar.jobCount} job{avatar.jobCount !== 1 ? 's' : ''}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

// ─── Object Card ──────────────────────────────────────────────────────

function ObjectCard({
  object,
  onDelete,
}: {
  object: ObjectRef
  onDelete: () => void
}) {
  const primaryImage = object.images?.find((img) => img.isPrimary)
  const hasImage = primaryImage?.storagePath != null

  return (
    <Card className="group overflow-hidden transition-shadow hover:shadow-md">
      {/* Thumbnail */}
      <div className="aspect-square bg-muted relative overflow-hidden">
        {hasImage ? (
          <img
            src={getImageUrl(primaryImage!)}
            alt={object.name}
            className="h-full w-full object-cover transition-transform group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-muted-foreground/60">
            <ImageOff className="h-12 w-12" />
          </div>
        )}
        {!hasImage && (
          <span
            className="absolute bottom-2 right-2 rounded-full bg-yellow-100/90 px-2 py-0.5 text-[10px] font-medium text-yellow-800 shadow"
            title="Reference image not yet generated by detection pipeline"
          >
            Pending
          </span>
        )}
        {/* Image count badge */}
        {object.images?.length > 0 && (
          <span className="absolute bottom-2 left-2 rounded-full bg-background/90 px-2 py-0.5 text-xs font-medium shadow">
            {object.images.length} image{object.images.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      <CardContent className="space-y-3 p-4">
        {/* Name */}
        <div>
          <h3 className="truncate font-semibold leading-tight">{object.name}</h3>
        </div>

        {/* Badges */}
        <div className="flex flex-wrap gap-1.5">
          {object.category && (
            <Badge variant="outline">
              <Tag className="h-3 w-3 mr-1" />
              {object.category}
            </Badge>
          )}
        </div>

        {/* Description snippet */}
        {object.description && (
          <p className="line-clamp-2 text-xs text-muted-foreground leading-relaxed">
            {object.description}
          </p>
        )}

        {/* Job count */}
        {object.jobCount > 0 && (
          <p className="text-xs text-muted-foreground">
            Used in {object.jobCount} job{object.jobCount !== 1 ? 's' : ''}
          </p>
        )}

        <div className="pt-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <Button
            variant="destructive"
            size="sm"
            className="w-full"
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Delete
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Edit Modal ──────────────────────────────────────────────────────

function EditAvatarModal({
  avatar,
  isOpen,
  onClose,
  onDeleteRequest,
}: {
  avatar: AvatarType
  isOpen: boolean
  onClose: () => void
  onDeleteRequest: () => void
}) {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  // ── Edit form state ─────────────────────────────────────────────
  const [editName, setEditName] = useState(avatar.name)
  const [editGender, setEditGender] = useState<AvatarGender>(avatar.gender)
  const [editBio, setEditBio] = useState(avatar.bio || '')
  const [editStrategy, setEditStrategy] = useState<ConsistencyStrategy>(avatar.consistencyStrategy)
  const [newFiles, setNewFiles] = useState<SelectedFile[]>([])
  const [posesQueued, setPosesQueued] = useState(false)
  const posesQueuedTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── Mutations ───────────────────────────────────────────────────
  const updateMutation = useMutation({
    mutationFn: async () => {
      const payload: UpdateAvatarRequest = {
        name: editName.trim(),
        gender: editGender,
        bio: editBio.trim() || undefined,
        consistencyStrategy: editStrategy,
      }
      const updated = await avatarsApi.update(avatar.id, payload)
      // Upload any new images
      for (const sf of newFiles) {
        if (sf.file) {
          await avatarsApi.uploadImage(avatar.id, sf.file)
        } else if (sf.asset) {
          const blob = await fetch(sf.asset.preview_path || sf.asset.file_path).then((r) =>
            r.blob(),
          )
          const fetchedFile = new File([blob], sf.asset.name, { type: blob.type })
          await avatarsApi.uploadImage(avatar.id, fetchedFile)
        }
      }
      return updated
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['avatars'] })
      // Revoke object URLs
      newFiles.forEach((sf) => URL.revokeObjectURL(sf.previewUrl))
      onClose()
    },
  })

  const setPrimaryMutation = useMutation({
    mutationFn: (imageId: string) => avatarsApi.setPrimaryImage(avatar.id, imageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['avatars'] })
    },
  })

  const deleteImageMutation = useMutation({
    mutationFn: (imageId: string) => avatarsApi.deleteImage(avatar.id, imageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['avatars'] })
    },
  })

  const generatePosesMutation = useMutation({
    mutationFn: () => avatarsApi.generatePoses(avatar.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['avatars'] })
      toast('Reference poses queued for generation', 'success')
      // Show "Queued!" on button for 3 seconds
      if (posesQueuedTimer.current) clearTimeout(posesQueuedTimer.current)
      setPosesQueued(true)
      posesQueuedTimer.current = setTimeout(() => setPosesQueued(false), 3000)
    },
    onError: (error: unknown) => {
      const msg = error instanceof Error ? error.message : 'Failed to generate reference poses.'
      toast(msg, 'error')
    },
  })

  const trainLoraMutation = useMutation({
    mutationFn: () => avatarsApi.trainLora(avatar.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['avatars'] })
    },
  })

  const isMutating =
    updateMutation.isPending ||
    setPrimaryMutation.isPending ||
    deleteImageMutation.isPending ||
    generatePosesMutation.isPending ||
    trainLoraMutation.isPending

  // ── File upload helpers ─────────────────────────────────────────
  const addFiles = useCallback((files: FileList | File[]) => {
    const newOnes: SelectedFile[] = Array.from(files)
      .filter((f) => f.type.startsWith('image/'))
      .map((file) => ({
        file,
        previewUrl: URL.createObjectURL(file),
      }))
    setNewFiles((prev) => [...prev, ...newOnes])
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      if (e.dataTransfer.files?.length) {
        addFiles(e.dataTransfer.files)
      }
    },
    [addFiles],
  )

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.length) {
        addFiles(e.target.files)
      }
      e.target.value = ''
    },
    [addFiles],
  )

  const removeNewFile = useCallback((index: number) => {
    setNewFiles((prev) => {
      const file = prev[index]
      if (file && file.file) {
        URL.revokeObjectURL(file.previewUrl)
      }
      return prev.filter((_, i) => i !== index)
    })
  }, [])

  // ── Submit ──────────────────────────────────────────────────────
  const canSave =
    editName.trim().length > 0 && editName.trim().length <= 255 && !isMutating

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSave) return
    updateMutation.mutate()
  }

  // Sorted images: primary first, then by sortOrder
  const sortedImages = [...avatar.images].sort((a, b) => {
    if (a.isPrimary) return -1
    if (b.isPrimary) return 1
    return a.sortOrder - b.sortOrder
  })

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open && !isMutating) onClose()
      }}
    >
      <DialogContent
        className="max-w-2xl max-h-[90vh] overflow-y-auto"
        onInteractOutside={(e) => {
          if (isMutating) e.preventDefault()
        }}
      >
        <DialogHeader>
          <DialogTitle>Edit Avatar</DialogTitle>
          <DialogDescription>
            Update details and manage reference images for &ldquo;{avatar.name}&rdquo;.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* ── Basic fields ─────────────────────────────────────── */}
          <div className="space-y-4">
            {/* Name */}
            <div className="space-y-2">
              <Label htmlFor="edit-avatar-name">Name *</Label>
              <Input
                id="edit-avatar-name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                placeholder="Enter avatar name"
                maxLength={255}
                required
              />
              <p className="text-xs text-muted-foreground">{editName.length}/255</p>
            </div>

            {/* Gender */}
            <div className="space-y-2">
              <Label htmlFor="edit-avatar-gender">Gender</Label>
              <Select
                value={editGender}
                onValueChange={(v) => setEditGender(v as AvatarGender)}
              >
                <SelectTrigger id="edit-avatar-gender">
                  <SelectValue placeholder="Select gender" />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(GENDER_LABELS) as AvatarGender[]).map((g) => (
                    <SelectItem key={g} value={g}>
                      {GENDER_LABELS[g]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Bio */}
            <div className="space-y-2">
              <Label htmlFor="edit-avatar-bio">Bio</Label>
              <Textarea
                id="edit-avatar-bio"
                value={editBio}
                onChange={(e) => setEditBio(e.target.value)}
                placeholder="Describe the character's appearance, personality, or backstory..."
                maxLength={2000}
                rows={3}
              />
              <p className="text-xs text-muted-foreground">
                {editBio.length}/2000 (optional)
              </p>
            </div>

            {/* Consistency strategy */}
            <div className="space-y-2">
              <Label htmlFor="edit-avatar-strategy">Consistency Strategy</Label>
              <Select
                value={editStrategy}
                onValueChange={(v) => setEditStrategy(v as ConsistencyStrategy)}
              >
                <SelectTrigger id="edit-avatar-strategy">
                  <SelectValue placeholder="Select strategy" />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(STRATEGY_LABELS) as ConsistencyStrategy[]).map((s) => (
                    <SelectItem key={s} value={s}>
                      {STRATEGY_LABELS[s]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <hr />

          {/* ── Existing Images ──────────────────────────────────── */}
          <div className="space-y-3">
            <Label>Reference Images ({avatar.images.length})</Label>

            {sortedImages.length === 0 && (
              <p className="text-sm text-muted-foreground">No images uploaded yet.</p>
            )}

            {sortedImages.length > 0 && (
              <div className="grid grid-cols-4 gap-2">
                {sortedImages.map((img) => (
                  <ImageThumbnail
                    key={img.id}
                    image={img}
                    avatarId={avatar.id}
                    isPrimary={img.isPrimary}
                    onSetPrimary={() => setPrimaryMutation.mutate(img.id)}
                    onDelete={() => deleteImageMutation.mutate(img.id)}
                    isBusy={isMutating}
                  />
                ))}
              </div>
            )}
          </div>

          {/* ── Upload More Images ────────────────────────────────── */}
          <div className="space-y-3">
            <Label>Add More Images</Label>

            {/* Drop zone */}
            <div
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-muted-foreground/25 p-4 text-center transition-colors hover:border-muted-foreground/50 cursor-pointer"
              onClick={() => fileInputRef.current?.click()}
            >
              <ImagePlus className="h-6 w-6 text-muted-foreground/50" />
              <p className="text-sm text-muted-foreground">
                Drag & drop or click to browse
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={handleFileInputChange}
              />
            </div>

            {/* New file previews */}
            {newFiles.length > 0 && (
              <div className="grid grid-cols-4 gap-2">
                {newFiles.map((sf, i) => (
                  <div
                    key={i}
                    className="relative aspect-square rounded-md overflow-hidden bg-muted group"
                  >
                    <img
                      src={sf.previewUrl}
                      alt={`New image ${i + 1}`}
                      className="h-full w-full object-cover"
                    />
                    <button
                      type="button"
                      onClick={() => removeNewFile(i)}
                      className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity"
                      disabled={isMutating}
                    >
                      <span className="text-white text-xs font-medium">Remove</span>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <hr />

          {/* ── Advanced Actions ──────────────────────────────────── */}
          <div className="space-y-3">
            <Label>Advanced</Label>

            <div className="flex flex-wrap gap-2">
              {/* Generate Reference Poses */}
              {avatar.images.length >= 1 && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => generatePosesMutation.mutate()}
                  disabled={isMutating}
                >
                  {generatePosesMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : posesQueued ? (
                    <Check className="h-4 w-4 mr-2 text-green-600" />
                  ) : (
                    <Wand2 className="h-4 w-4 mr-2" />
                  )}
                  {posesQueued ? 'Queued!' : 'Generate Reference Poses'}
                </Button>
              )}

              {/* Train LoRA */}
              {avatar.consistencyStrategy === 'lora' && (
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => trainLoraMutation.mutate()}
                    disabled={
                      isMutating ||
                      avatar.loraTrainingStatus === 'training'
                    }
                  >
                    {trainLoraMutation.isPending ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Cpu className="h-4 w-4 mr-2" />
                    )}
                    Train LoRA
                  </Button>
                  <Badge
                    variant={
                      avatar.loraTrainingStatus === 'training'
                        ? 'secondary'
                        : LORA_STATUS_VARIANTS[avatar.loraTrainingStatus]
                    }
                    className="text-xs"
                  >
                    {avatar.loraTrainingStatus === 'training' && (
                      <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                    )}
                    {LORA_STATUS_LABELS[avatar.loraTrainingStatus] ||
                      avatar.loraTrainingStatus}
                  </Badge>
                </div>
              )}
            </div>

            {generatePosesMutation.isError && (
              <p className="text-sm text-destructive">
                {(generatePosesMutation.error as Error)?.message ||
                  'Failed to generate reference poses.'}
              </p>
            )}
            {trainLoraMutation.isError && (
              <p className="text-sm text-destructive">
                {(trainLoraMutation.error as Error)?.message || 'Failed to start LoRA training.'}
              </p>
            )}

            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={onDeleteRequest}
              disabled={isMutating}
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Delete Avatar
            </Button>
          </div>

          {/* ── Error display ─────────────────────────────────────── */}
          {updateMutation.isError && (
            <p className="text-sm text-destructive">
              {(updateMutation.error as Error)?.message || 'Failed to update avatar.'}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={isMutating}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSave}>
              {updateMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save Changes'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ─── Image Thumbnail Component ────────────────────────────────────────

function ImageThumbnail({
  image,
  avatarId,
  isPrimary,
  onSetPrimary,
  onDelete,
  isBusy,
}: {
  image: AvatarImage
  avatarId: string
  isPrimary: boolean
  onSetPrimary: () => void
  onDelete: () => void
  isBusy: boolean
}) {
  return (
    <div className="relative aspect-square rounded-md overflow-hidden bg-muted group">
      {image.storagePath ? (
        <img
          src={getImageUrl(image, avatarId)}
          alt="Reference"
          className="h-full w-full object-cover"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-muted-foreground">
          <User className="h-6 w-6" />
        </div>
      )}

      {/* Primary badge */}
      {isPrimary && (
        <span className="absolute top-1 left-1 rounded bg-primary/90 px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
          Primary
        </span>
      )}

      {/* Hover overlay with actions */}
      <div className="absolute inset-0 flex items-center justify-center gap-1 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity">
        {!isPrimary && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onSetPrimary()
            }}
            disabled={isBusy}
            className="rounded bg-white/20 p-1.5 text-white hover:bg-white/30 transition-colors"
            title="Set as primary"
          >
            <Star className="h-3.5 w-3.5" />
          </button>
        )}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          disabled={isBusy}
          className="rounded bg-white/20 p-1.5 text-white hover:bg-destructive/70 transition-colors"
          title="Delete image"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

// ─── Page component ──────────────────────────────────────────────────

export default function Avatars() {
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // ── Tab state ─────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<'avatars' | 'objects'>('avatars')

  // ── Edit state ─────────────────────────────────────────────────
  const [selectedAvatar, setSelectedAvatar] = useState<AvatarType | null>(null)
  const [showEdit, setShowEdit] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  // ── Object state ───────────────────────────────────────────────
  const [selectedObject, setSelectedObject] = useState<ObjectRef | null>(null)
  const [showObjectDeleteConfirm, setShowObjectDeleteConfirm] = useState(false)

  // ── Object create state ──────────────────────────────────────────
  const [showCreateObject, setShowCreateObject] = useState(false)
  const [objectName, setObjectName] = useState('')
  const [objectDescription, setObjectDescription] = useState('')
  const [objectCategory, setObjectCategory] = useState('')
  const [objectFiles, setObjectFiles] = useState<SelectedFile[]>([])
  const objectFileInputRef = useRef<HTMLInputElement>(null)
  const [showObjectAssetPicker, setShowObjectAssetPicker] = useState(false)

  // ── Create form state ───────────────────────────────────────────
  const [name, setName] = useState('')
  const [gender, setGender] = useState<AvatarGender>('Male')
  const [bio, setBio] = useState('')
  const [consistencyStrategy, setConsistencyStrategy] =
    useState<ConsistencyStrategy>('ip_adapter')
  const [selectedFiles, setSelectedFiles] = useState<SelectedFile[]>([])

  // Asset picker state
  const [showAssetPicker, setShowAssetPicker] = useState(false)

  // Query
  const { data, isLoading } = useQuery({
    queryKey: ['avatars'],
    queryFn: () => avatarsApi.list(),
  })

  const avatars = data?.avatars ?? []

  // ── Objects query ─────────────────────────────────────────────
  const { data: objectsData, isLoading: objectsLoading } = useQuery({
    queryKey: ['objects'],
    queryFn: () => objectsApi.list(),
    enabled: activeTab === 'objects',
  })

  const objects = objectsData?.objects ?? []

  // ── Create mutation ─────────────────────────────────────────────
  const createMutation = useMutation({
    mutationFn: async () => {
      const payload: CreateAvatarRequest = {
        name: name.trim(),
        gender,
        bio: bio.trim() || undefined,
        consistencyStrategy,
      }
      const avatar = await avatarsApi.create(payload)
      for (const sf of selectedFiles) {
        if (sf.file) {
          await avatarsApi.uploadImage(avatar.id, sf.file)
        } else if (sf.asset) {
          const blob = await fetch(sf.asset.preview_path || sf.asset.file_path).then((r) =>
            r.blob(),
          )
          const fetchedFile = new File([blob], sf.asset.name, { type: blob.type })
          await avatarsApi.uploadImage(avatar.id, fetchedFile)
        }
      }
      return avatar
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['avatars'] })
      resetCreateForm()
      setShowCreate(false)
    },
  })

  // ── Delete mutation ─────────────────────────────────────────────
  const deleteMutation = useMutation({
    mutationFn: (id: string) => avatarsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['avatars'] })
      setShowDeleteConfirm(false)
      setSelectedAvatar(null)
      setShowEdit(false)
    },
  })

  // ── Object delete mutation ─────────────────────────────────────
  const deleteObjectMutation = useMutation({
    mutationFn: (id: string) => objectsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      setShowObjectDeleteConfirm(false)
      setSelectedObject(null)
    },
  })

  // ── Object create mutation ──────────────────────────────────────
  const createObjectMutation = useMutation({
    mutationFn: async () => {
      const payload: CreateObjectRefRequest = {
        name: objectName.trim(),
        description: objectDescription.trim() || undefined,
        category: objectCategory.trim() || undefined,
      }
      const obj = await objectsApi.create(payload)
      for (const sf of objectFiles) {
        if (sf.file) {
          await objectsApi.uploadImage(obj.id, sf.file)
        } else if (sf.asset) {
          const blob = await fetch(sf.asset.preview_path || sf.asset.file_path).then((r) =>
            r.blob(),
          )
          const fetchedFile = new File([blob], sf.asset.name, { type: blob.type })
          await objectsApi.uploadImage(obj.id, fetchedFile)
        }
      }
      return obj
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      resetObjectCreateForm()
      setShowCreateObject(false)
    },
  })

  // ── Create form helpers ─────────────────────────────────────────
  const resetCreateForm = () => {
    setName('')
    setGender('Male')
    setBio('')
    setConsistencyStrategy('ip_adapter')
    selectedFiles.forEach((sf) => URL.revokeObjectURL(sf.previewUrl))
    setSelectedFiles([])
    createMutation.reset()
  }

  const handleCreateDialogClose = () => {
    if (!createMutation.isPending) {
      resetCreateForm()
      setShowCreate(false)
    }
  }

  // ── Object create form helpers ──────────────────────────────────
  const resetObjectCreateForm = () => {
    setObjectName('')
    setObjectDescription('')
    setObjectCategory('')
    objectFiles.forEach((sf) => URL.revokeObjectURL(sf.previewUrl))
    setObjectFiles([])
    createObjectMutation.reset()
  }

  const handleObjectCreateDialogClose = () => {
    if (!createObjectMutation.isPending) {
      resetObjectCreateForm()
      setShowCreateObject(false)
    }
  }

  const addObjectFiles = useCallback((files: FileList | File[]) => {
    const newFilesArr: SelectedFile[] = Array.from(files)
      .filter((f) => f.type.startsWith('image/'))
      .map((file) => ({
        file,
        previewUrl: URL.createObjectURL(file),
      }))
    setObjectFiles((prev) => [...prev, ...newFilesArr])
  }, [])

  const handleObjectDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      addObjectFiles(e.dataTransfer.files)
    },
    [addObjectFiles],
  )

  const handleObjectFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.length) {
        addObjectFiles(e.target.files)
      }
      e.target.value = ''
    },
    [addObjectFiles],
  )

  const handleObjectAssetSelect = useCallback((asset: MediaAsset) => {
    const previewUrl = asset.preview_path || asset.file_path
    setObjectFiles((prev) => [...prev, { asset, previewUrl }])
    setShowObjectAssetPicker(false)
  }, [])

  const removeObjectFile = useCallback((index: number) => {
    setObjectFiles((prev) => {
      const file = prev[index]
      if (file && file.file) {
        URL.revokeObjectURL(file.previewUrl)
      }
      return prev.filter((_, i) => i !== index)
    })
  }, [])

  const canSubmitObject =
    objectName.trim().length > 0 && objectName.trim().length <= 255 && !createObjectMutation.isPending

  const handleObjectSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmitObject) return
    createObjectMutation.mutate()
  }

  // ── Edit handlers ───────────────────────────────────────────────
  const handleCardClick = useCallback((avatar: AvatarType) => {
    setSelectedAvatar(avatar)
    setShowEdit(true)
  }, [])

  const handleEditClose = useCallback(() => {
    setShowEdit(false)
    // Delay clearing so modal can animate out
    setTimeout(() => setSelectedAvatar(null), 200)
  }, [])

  const handleDeleteClick = useCallback(() => {
    setShowDeleteConfirm(true)
  }, [])

  // ── File upload handlers (create) ───────────────────────────────
  const addFiles = useCallback((files: FileList | File[]) => {
    const newFilesArr: SelectedFile[] = Array.from(files)
      .filter((f) => f.type.startsWith('image/'))
      .map((file) => ({
        file,
        previewUrl: URL.createObjectURL(file),
      }))
    setSelectedFiles((prev) => [...prev, ...newFilesArr])
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      if (e.dataTransfer.files?.length) {
        addFiles(e.dataTransfer.files)
      }
    },
    [addFiles],
  )

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.length) {
        addFiles(e.target.files)
      }
      e.target.value = ''
    },
    [addFiles],
  )

  const handleAssetSelect = useCallback((asset: MediaAsset) => {
    const previewUrl = asset.preview_path || asset.file_path
    setSelectedFiles((prev) => [...prev, { asset, previewUrl }])
    setShowAssetPicker(false)
  }, [])

  const removeFile = useCallback((index: number) => {
    setSelectedFiles((prev) => {
      const file = prev[index]
      if (file && file.file) {
        URL.revokeObjectURL(file.previewUrl)
      }
      return prev.filter((_, i) => i !== index)
    })
  }, [])

  // ── Submit (create) ─────────────────────────────────────────────
  const canSubmit =
    name.trim().length > 0 && name.trim().length <= 255 && !createMutation.isPending

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    createMutation.mutate()
  }

  // ── Render ─────────────────────────────────────────────────────
  return (
    <div className="h-full flex flex-col gap-2.5 p-2.5">
      {/* ── Sticky header: tabs + page title ─────────────────────── */}
      <div className="shrink-0 flex flex-col gap-2.5">
        {/* Tab Navigation */}
        <div className="flex items-center gap-1 bg-muted rounded-lg p-1 w-fit">
          <button
            onClick={() => setActiveTab('avatars')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'avatars'
                ? 'bg-background shadow-sm text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <User className="h-4 w-4 inline mr-1.5" />
            Avatars
          </button>
          <button
            onClick={() => setActiveTab('objects')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'objects'
                ? 'bg-background shadow-sm text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Box className="h-4 w-4 inline mr-1.5" />
            Objects
          </button>
        </div>

        {/* Avatars Header */}
        {activeTab === 'avatars' && (
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold">Avatars</h1>
              <p className="text-muted-foreground">
                Create consistent characters for your videos
              </p>
            </div>
            <Button onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Create Avatar
            </Button>
          </div>
        )}

        {/* Objects Header */}
        {activeTab === 'objects' && (
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold">Objects</h1>
              <p className="text-muted-foreground">
                Objects auto-detected from your scenes
              </p>
            </div>
            <Button onClick={() => setShowCreateObject(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Create Object
            </Button>
          </div>
        )}
      </div>

      {/* ── Scrollable content area ──────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-y-auto pb-2.5">
        {/* ── Avatars Tab ───────────────────────────────────────── */}
        {activeTab === 'avatars' && (
          <>
            {/* Loading */}
            {isLoading && (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            )}

            {/* Empty state */}
            {!isLoading && avatars.length === 0 && (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <User className="h-16 w-16 text-muted-foreground/40 mb-4" />
                <h2 className="text-xl font-semibold mb-2">No avatars yet</h2>
                <p className="text-muted-foreground max-w-sm mb-6">
                  Create your first avatar to add consistent characters to your
                  videos.
                </p>
                <Button onClick={() => setShowCreate(true)}>
                  <Plus className="h-4 w-4 mr-2" />
                  Create Avatar
                </Button>
              </div>
            )}

            {/* Avatar grid */}
            {!isLoading && avatars.length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
                {avatars.map((avatar) => (
                  <AvatarCard
                    key={avatar.id}
                    avatar={avatar}
                    onClick={handleCardClick}
                  />
                ))}
              </div>
            )}
          </>
        )}

        {/* ── Objects Tab ───────────────────────────────────────── */}
        {activeTab === 'objects' && (
          <>
            {/* Loading */}
            {objectsLoading && (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            )}

            {/* Empty state */}
            {!objectsLoading && objects.length === 0 && (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <Box className="h-16 w-16 text-muted-foreground/40 mb-4" />
                <h2 className="text-xl font-semibold mb-2">No objects yet</h2>
                <p className="text-muted-foreground max-w-sm mb-6">
                  Objects are automatically detected when you create scenes.
                  They will appear here once detected.
                </p>
              </div>
            )}

            {/* Object grid */}
            {!objectsLoading && objects.length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
                {objects.map((obj) => (
                  <ObjectCard
                    key={obj.id}
                    object={obj}
                    onDelete={() => {
                      setSelectedObject(obj)
                      setShowObjectDeleteConfirm(true)
                    }}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* ── Create Modal ──────────────────────────────────────────── */}
      <Dialog
        open={showCreate}
        onOpenChange={(open) => {
          if (!open) handleCreateDialogClose()
        }}
      >
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Create Avatar</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Name */}
            <div className="space-y-2">
              <Label htmlFor="avatar-name">Name *</Label>
              <Input
                id="avatar-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Enter avatar name"
                maxLength={255}
                required
              />
              <p className="text-xs text-muted-foreground">{name.length}/255</p>
            </div>

            {/* Gender */}
            <div className="space-y-2">
              <Label htmlFor="avatar-gender">Gender</Label>
              <Select
                value={gender}
                onValueChange={(v) => setGender(v as AvatarGender)}
              >
                <SelectTrigger id="avatar-gender">
                  <SelectValue placeholder="Select gender" />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(GENDER_LABELS) as AvatarGender[]).map((g) => (
                    <SelectItem key={g} value={g}>
                      {GENDER_LABELS[g]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Bio */}
            <div className="space-y-2">
              <Label htmlFor="avatar-bio">Bio</Label>
              <Textarea
                id="avatar-bio"
                value={bio}
                onChange={(e) => setBio(e.target.value)}
                placeholder="Describe the character's appearance, personality, or backstory..."
                maxLength={2000}
                rows={3}
              />
              <p className="text-xs text-muted-foreground">
                {bio.length}/2000 (optional)
              </p>
            </div>

            {/* Consistency strategy */}
            <div className="space-y-2">
              <Label htmlFor="avatar-strategy">Consistency Strategy</Label>
              <Select
                value={consistencyStrategy}
                onValueChange={(v) => setConsistencyStrategy(v as ConsistencyStrategy)}
              >
                <SelectTrigger id="avatar-strategy">
                  <SelectValue placeholder="Select strategy" />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(STRATEGY_LABELS) as ConsistencyStrategy[]).map((s) => (
                    <SelectItem key={s} value={s}>
                      {STRATEGY_LABELS[s]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Image upload area */}
            <div className="space-y-2">
              <Label>Reference Images</Label>
              <p className="text-xs text-muted-foreground">
                Upload images of the character to improve consistency.
              </p>

              {/* Drop zone */}
              <div
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
                className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-muted-foreground/25 p-6 text-center transition-colors hover:border-muted-foreground/50 cursor-pointer"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="h-8 w-8 text-muted-foreground/50" />
                <p className="text-sm text-muted-foreground">
                  Drag & drop images here, or click to browse
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  className="hidden"
                  onChange={handleFileInputChange}
                />
              </div>

              {/* From Media Library button */}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full"
                onClick={() => setShowAssetPicker(true)}
              >
                <FolderOpen className="h-4 w-4 mr-2" />
                From Media Library
              </Button>

              {/* Previews */}
              {selectedFiles.length > 0 && (
                <div className="grid grid-cols-4 gap-2 mt-2">
                  {selectedFiles.map((sf, i) => (
                    <div
                      key={i}
                      className="relative aspect-square rounded-md overflow-hidden bg-muted group"
                    >
                      <img
                        src={sf.previewUrl}
                        alt={`Reference ${i + 1}`}
                        className="h-full w-full object-cover"
                      />
                      <button
                        type="button"
                        onClick={() => removeFile(i)}
                        className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <span className="text-white text-xs font-medium">
                          Remove
                        </span>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Error display */}
            {createMutation.isError && (
              <p className="text-sm text-destructive">
                {(createMutation.error as Error)?.message ||
                  'Failed to create avatar. Please try again.'}
              </p>
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={handleCreateDialogClose}
                disabled={createMutation.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={!canSubmit}>
                {createMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Creating...
                  </>
                ) : (
                  'Create Avatar'
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── Create Object Modal ───────────────────────────────────── */}
      <Dialog
        open={showCreateObject}
        onOpenChange={(open) => {
          if (!open) handleObjectCreateDialogClose()
        }}
      >
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Create Object</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleObjectSubmit} className="space-y-4">
            {/* Name */}
            <div className="space-y-2">
              <Label htmlFor="object-name">Name *</Label>
              <Input
                id="object-name"
                value={objectName}
                onChange={(e) => setObjectName(e.target.value)}
                placeholder="Enter object name"
                maxLength={255}
                required
              />
              <p className="text-xs text-muted-foreground">{objectName.length}/255</p>
            </div>

            {/* Description */}
            <div className="space-y-2">
              <Label htmlFor="object-description">Description</Label>
              <Textarea
                id="object-description"
                value={objectDescription}
                onChange={(e) => setObjectDescription(e.target.value)}
                placeholder="Describe the object's appearance or purpose..."
                maxLength={2000}
                rows={3}
              />
              <p className="text-xs text-muted-foreground">
                {objectDescription.length}/2000 (optional)
              </p>
            </div>

            {/* Category */}
            <div className="space-y-2">
              <Label htmlFor="object-category">Category</Label>
              <Input
                id="object-category"
                value={objectCategory}
                onChange={(e) => setObjectCategory(e.target.value)}
                placeholder="e.g., vehicle, weapon, furniture"
                maxLength={100}
              />
              <p className="text-xs text-muted-foreground">(optional)</p>
            </div>

            {/* Image upload area */}
            <div className="space-y-2">
              <Label>Reference Images</Label>
              <p className="text-xs text-muted-foreground">
                Upload images of the object to improve recognition.
              </p>

              {/* Drop zone */}
              <div
                onDrop={handleObjectDrop}
                onDragOver={(e) => e.preventDefault()}
                className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-muted-foreground/25 p-6 text-center transition-colors hover:border-muted-foreground/50 cursor-pointer"
                onClick={() => objectFileInputRef.current?.click()}
              >
                <Upload className="h-8 w-8 text-muted-foreground/50" />
                <p className="text-sm text-muted-foreground">
                  Drag & drop images here, or click to browse
                </p>
                <input
                  ref={objectFileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  className="hidden"
                  onChange={handleObjectFileInputChange}
                />
              </div>

              {/* From Media Library button */}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full"
                onClick={() => setShowObjectAssetPicker(true)}
              >
                <FolderOpen className="h-4 w-4 mr-2" />
                From Media Library
              </Button>

              {/* Previews */}
              {objectFiles.length > 0 && (
                <div className="grid grid-cols-4 gap-2 mt-2">
                  {objectFiles.map((sf, i) => (
                    <div
                      key={i}
                      className="relative aspect-square rounded-md overflow-hidden bg-muted group"
                    >
                      <img
                        src={sf.previewUrl}
                        alt={`Reference ${i + 1}`}
                        className="h-full w-full object-cover"
                      />
                      <button
                        type="button"
                        onClick={() => removeObjectFile(i)}
                        className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <span className="text-white text-xs font-medium">
                          Remove
                        </span>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Error display */}
            {createObjectMutation.isError && (
              <p className="text-sm text-destructive">
                {(createObjectMutation.error as Error)?.message ||
                  'Failed to create object. Please try again.'}
              </p>
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={handleObjectCreateDialogClose}
                disabled={createObjectMutation.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={!canSubmitObject}>
                {createObjectMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Creating...
                  </>
                ) : (
                  'Create Object'
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── Edit Modal ────────────────────────────────────────────── */}
      {selectedAvatar && (
        <EditAvatarModal
          avatar={selectedAvatar}
          isOpen={showEdit}
          onClose={handleEditClose}
          onDeleteRequest={handleDeleteClick}
        />
      )}

      {/* ── Delete Confirmation ───────────────────────────────────── */}
      {selectedAvatar && (
        <DeleteConfirmationModal
          isOpen={showDeleteConfirm}
          onClose={() => setShowDeleteConfirm(false)}
          onConfirm={() => deleteMutation.mutate(selectedAvatar.id)}
          title="Delete Avatar"
          message={`Are you sure you want to delete "${selectedAvatar.name}"? Avatars used in existing videos will retain their reference.`}
          itemsToDelete={{ avatar: 1, images: selectedAvatar.images.length }}
          warning="This action cannot be undone. The avatar and all associated images will be permanently deleted."
          isLoading={deleteMutation.isPending}
        />
      )}

      {/* ── Object Delete Confirmation ─────────────────────────────── */}
      {selectedObject && (
        <DeleteConfirmationModal
          isOpen={showObjectDeleteConfirm}
          onClose={() => setShowObjectDeleteConfirm(false)}
          onConfirm={() => deleteObjectMutation.mutate(selectedObject.id)}
          title="Delete Object"
          message={`Are you sure you want to delete "${selectedObject.name}"? Objects used in existing videos will retain their reference.`}
          itemsToDelete={{ object: 1, images: selectedObject.images.length }}
          warning="This action cannot be undone."
          isLoading={deleteObjectMutation.isPending}
        />
      )}

      {/* Asset picker modal */}
      <AssetPickerModal
        isOpen={showAssetPicker}
        onClose={() => setShowAssetPicker(false)}
        onSelect={handleAssetSelect}
      />

      {/* Object asset picker modal */}
      <AssetPickerModal
        isOpen={showObjectAssetPicker}
        onClose={() => setShowObjectAssetPicker(false)}
        onSelect={handleObjectAssetSelect}
      />
    </div>
  )
}
