import { useState, useMemo, useCallback, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Loader2, Search, Upload, X, Image as ImageIcon } from 'lucide-react'
import api, { modelsApi, type ModelConfig } from '../api/client'
import { Button } from './ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog'
import { Input } from './ui/input'
import { Label } from './ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs'
import { Textarea } from './ui/textarea'
import { AssetPickerModal } from './media/AssetPickerModal'
import { useUploadAssets } from '../hooks/useMedia'
import type { MediaAsset } from '../api/types/media'

interface ModelOption {
  id: string
  name: string
  provider: string
  description?: string
  capabilities?: Record<string, boolean>
  costConfig?: Record<string, unknown> | null
  resolutions?: string[] | null
  sizeParamFamily?: string | null
}

export interface QuickCreateMediaProps {
  triggerClassName?: string
  onSuccess?: () => void
}

const ARRAY_CAP_MAP: Record<string, Record<string, boolean>> = {
  'text-to-image': { accepts_text: true, outputs_image: true },
  'image-to-image': { accepts_image: true, outputs_image: true },
  'text-to-video': { accepts_text: true, outputs_video: true },
  'image-to-video': { accepts_image: true, outputs_video: true },
  'video-to-video': { accepts_video: true, outputs_video: true },
  'scene-to-video': { accepts_video: true, outputs_video: true },
  'audio-to-video': { accepts_audio: true, outputs_video: true },
  chat: { accepts_text: true, outputs_text: true },
}

function toModelOption(m: ModelConfig): ModelOption {
  let caps: Record<string, boolean> | undefined
  if (Array.isArray(m.capabilities)) {
    caps = {}
    for (const c of m.capabilities) {
      Object.assign(caps, ARRAY_CAP_MAP[c] || {})
    }
  } else {
    caps = m.capabilities
  }
  return {
    id: m.id,
    name: m.display_name || m.id,
    provider: m.provider,
    description: m.description,
    capabilities: caps,
    costConfig: m.cost_config,
    resolutions: m.resolutions ?? null,
    sizeParamFamily: m.size_param_family ?? null,
  }
}

function hasCapability(
  caps: Record<string, boolean> | string[] | undefined,
  ...keys: string[]
): boolean {
  if (!caps) return false
  if (Array.isArray(caps)) {
    return caps.some(v => keys.includes(v))
  }
  return keys.some((k) => caps[k] === true)
}

const RESOLUTION_LABELS: Record<string, string> = {
  '1536x1536': '1:1 square (1536×1536)',
  '2688x1536': '16:9 landscape (2688×1536)',
  '1536x2688': '9:16 portrait (1536×2688)',
  '2048x1536': '4:3 landscape (2048×1536)',
  '1536x2048': '3:4 portrait (1536×2048)',
  '1024x1024': '1:1 square (1024×1024)',
  '1024x1536': '9:16 portrait (1024×1536)',
  '1536x1024': '16:9 landscape (1536×1024)',
  '1440x1440': '1:1 square (1440×1440)',
  '2560x1440': '16:9 landscape (2560×1440)',
  '1440x2560': '9:16 portrait (1440×2560)',
  '2048x1440': '4:3 landscape (2048×1440)',
  '1440x2048': '3:4 portrait (1440×2048)',
  '848x1264':  '3:4 portrait (848×1264)',
  '1264x848':  '4:3 landscape (1264×848)',
  '768x1376':  'portrait (768×1376)',
  '1376x768':  'landscape (1376×768)',
}

function resolutionLabel(r: string): string {
  return RESOLUTION_LABELS[r] ?? r
}

export default function QuickCreateMedia({ triggerClassName, onSuccess }: QuickCreateMediaProps) {
  const [open, setOpen] = useState(false)
  const [selectedModel, setSelectedModel] = useState<ModelOption | null>(null)
  const [step, setStep] = useState<'select' | 'configure'>('select')

  const [aspectRatio, setAspectRatio] = useState('1:1')
  const [duration, setDuration] = useState(5)
  const [negativePrompt, setNegativePrompt] = useState('')
  const [seed, setSeed] = useState('')
  const [prompt, setPrompt] = useState('')
  const [title, setTitle] = useState('')
  const [resolution, setResolution] = useState('1536x2688')
  const [showAssetPicker, setShowAssetPicker] = useState(false)
  const [imageAsset, setImageAsset] = useState<MediaAsset | null>(null)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [providerFilter, setProviderFilter] = useState('all')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const uploadMutation = useUploadAssets()

  const { data: models, isLoading } = useQuery({
    queryKey: ['availableModels'],
    queryFn: () => modelsApi.getAvailableModels(),
  })

  const imageModels = useMemo<ModelOption[]>(
    () => models?.image_models?.map(toModelOption) ?? [],
    [models],
  )
  const videoModels = useMemo<ModelOption[]>(
    () => models?.video_models?.map(toModelOption) ?? [],
    [models],
  )

  const filteredImageModels = useMemo(() => {
    return imageModels.filter(m => {
      const matchesSearch = !searchQuery ||
        m.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.id.toLowerCase().includes(searchQuery.toLowerCase())
      const matchesProvider = providerFilter === 'all' || m.provider === providerFilter
      return matchesSearch && matchesProvider
    })
  }, [imageModels, searchQuery, providerFilter])

  const filteredVideoModels = useMemo(() => {
    return videoModels.filter(m => {
      const matchesSearch = !searchQuery ||
        m.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.id.toLowerCase().includes(searchQuery.toLowerCase())
      const matchesProvider = providerFilter === 'all' || m.provider === providerFilter
      return matchesSearch && matchesProvider
    })
  }, [videoModels, searchQuery, providerFilter])

  const uniqueProviders = useMemo(() => {
    const providers = new Set<string>()
    for (const m of [...imageModels, ...videoModels]) {
      if (m.provider) providers.add(m.provider)
    }
    return Array.from(providers).sort()
  }, [imageModels, videoModels])

  const caps = selectedModel?.capabilities
  const usesPixelResolution = !!(selectedModel?.sizeParamFamily && selectedModel.sizeParamFamily !== 'ratio')
  const availableResolutions = selectedModel?.resolutions ?? null
  const acceptsText = caps ? hasCapability(caps, 'accepts_text') : true
  const acceptsImage = hasCapability(caps, 'accepts_image')
  const outputsImage = hasCapability(caps, 'outputs_image')
  const outputsVideo = hasCapability(caps, 'outputs_video')
  const isImageOnly = acceptsImage && !acceptsText
  const promptRequired = acceptsText
  const imageRequired = isImageOnly

  const resetImage = useCallback(() => {
    if (imagePreview) URL.revokeObjectURL(imagePreview)
    setImageAsset(null)
    setImageFile(null)
    setImagePreview(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [imagePreview])

  const handleModelSelect = (model: ModelOption) => {
    setSelectedModel(model)
    resetImage()
    setTitle('')
    if (model.resolutions && model.sizeParamFamily !== 'ratio') {
      const portrait = model.resolutions.find(r => {
        const parts = r.split('x').map(Number)
        return parts.length === 2 && parts[1] > parts[0]
      })
      setResolution(portrait ?? model.resolutions[0])
    }
    setStep('configure')
  }

  const handleAssetSelect = useCallback((asset: MediaAsset) => {
    setImageAsset(asset)
    setImageFile(null)
    setImagePreview(asset.preview_path ?? null)
    setShowAssetPicker(false)
  }, [])

  const uploadFile = useCallback(async (file: File) => {
    setImageFile(file)
    setImageAsset(null)
    setImagePreview(URL.createObjectURL(file))
    setIsUploading(true)
    try {
      const assets = await uploadMutation.mutateAsync({ files: [file] })
      if (assets.length > 0) {
        setImageAsset(assets[0])
        setImageFile(null)
        setImagePreview(assets[0].preview_path ?? null)
      }
    } catch {
      void 0
    } finally {
      setIsUploading(false)
    }
  }, [uploadMutation])

  const handleFileDrop = useCallback(async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    const file = e.dataTransfer.files[0]
    if (!file || !file.type.startsWith('image/')) return
    await uploadFile(file)
  }, [uploadFile])

  const handleFileInput = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    await uploadFile(file)
  }, [uploadFile])

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  const handleGenerate = async () => {
    if (!selectedModel) return
    if (promptRequired && !prompt.trim()) return
    if (imageRequired && !imageAsset && !imageFile) return
    setSubmitting(true)
    try {
      const payload: Record<string, unknown> = {
        model_id: selectedModel.id,
        prompt: prompt.trim() || '',
        aspect_ratio: usesPixelResolution ? resolution : aspectRatio,
        negative_prompt: negativePrompt || undefined,
        seed: seed ? Number(seed) : undefined,
        title: title.trim() || undefined,
      }
      if (outputsVideo || selectedModel.provider === 'video') {
        payload.duration = duration
      }
      if (imageAsset?.file_path) {
        payload.image_path = imageAsset.file_path
      } else if (imageFile) {
        const base64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = () => {
            const result = reader.result as string
            resolve(result.split(',')[1] ?? result)
          }
          reader.onerror = reject
          reader.readAsDataURL(imageFile)
        })
        payload.image = base64
        payload.image_mime = imageFile.type
      }
      await api.post('/media/generate', payload)
      setOpen(false)
      setStep('select')
      setPrompt('')
      resetImage()
      onSuccess?.()
    } finally {
      setSubmitting(false)
    }
  }

  const getEstimatedCost = () => {
    if (!selectedModel?.costConfig) return null
    const cc = selectedModel.costConfig
    if (cc.cost === 0) return 'Free (local)'
    const credits =
      (cc.credits_per_image as number) ||
      (cc.credits_per_second as number) ||
      (cc.compute_points as number) ||
      0
    const total = credits * duration
    const currency = (cc.currency as string) || 'credits'
    return `~${total} ${currency}`
  }

  const estimatedCost = getEstimatedCost()

  const handleOpen = useCallback(() => {
    setStep('select')
    setSelectedModel(null)
    setAspectRatio('1:1')
    setDuration(5)
    setNegativePrompt('')
    setSeed('')
    setPrompt('')
    setTitle('')
    setResolution('1536x2688')
    setShowAssetPicker(false)
    resetImage()
    setIsUploading(false)
    setSubmitting(false)
    setSearchQuery('')
    setProviderFilter('all')
    setOpen(true)
  }, [resetImage])

  return (
    <>
      <Button onClick={handleOpen} className={triggerClassName}>
        <Plus className="h-4 w-4 mr-2" />
        Create Media
      </Button>

      {showAssetPicker && (
        <AssetPickerModal
          isOpen={showAssetPicker}
          onClose={() => setShowAssetPicker(false)}
          onSelect={handleAssetSelect}
        />
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Create Media</DialogTitle>
            <DialogDescription>
              Select a model and configure settings to generate media.
            </DialogDescription>
          </DialogHeader>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : step === 'select' ? (
            <>
            <div className="flex gap-2 mb-3">
              <div className="relative flex-1">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search models..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  className="pl-8"
                />
              </div>
              <Select value={providerFilter} onValueChange={setProviderFilter}>
                <SelectTrigger className="w-40">
                  <SelectValue placeholder="All providers" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All providers</SelectItem>
                  {uniqueProviders.map(p => (
                    <SelectItem key={p} value={p}>{p}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Tabs defaultValue="image">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="image">Image Models</TabsTrigger>
                <TabsTrigger value="video">Video Models</TabsTrigger>
              </TabsList>
              <TabsContent value="image" className="space-y-2 mt-4 max-h-64 overflow-y-auto">
                {filteredImageModels.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-8 text-center">
                    No image models available
                  </p>
                ) : (
                  filteredImageModels.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => handleModelSelect(m)}
                      className="w-full text-left p-3 rounded-lg border hover:border-primary transition-colors"
                    >
                      <div className="font-medium">{m.name}</div>
                      {m.description && (
                        <div className="text-xs text-muted-foreground">{m.description}</div>
                      )}
                    </button>
                  ))
                )}
              </TabsContent>
              <TabsContent value="video" className="space-y-2 mt-4 max-h-64 overflow-y-auto">
                {filteredVideoModels.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-8 text-center">
                    No video models available
                  </p>
                ) : (
                  filteredVideoModels.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => handleModelSelect(m)}
                      className="w-full text-left p-3 rounded-lg border hover:border-primary transition-colors"
                    >
                      <div className="font-medium">{m.name}</div>
                      {m.description && (
                        <div className="text-xs text-muted-foreground">{m.description}</div>
                      )}
                    </button>
                  ))
                )}
              </TabsContent>
            </Tabs>
            </>
          ) : (
            <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
              <button
                onClick={() => {
                  setStep('select')
                  resetImage()
                }}
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                &larr; Back to model selection
              </button>
              <div className="font-medium">{selectedModel?.name}</div>

              {caps && (
                <div className="flex flex-wrap gap-1">
                  <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                    Accepts: {[
                      acceptsText && 'text',
                      acceptsImage && 'image',
                    ].filter(Boolean).join(', ') || 'none'}
                  </span>
                  <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                    &rarr; Outputs: {[
                      outputsImage && 'image',
                      outputsVideo && 'video',
                    ].filter(Boolean).join(', ') || 'none'}
                  </span>
                </div>
              )}

              <div>
                <Label>Title (optional)</Label>
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Enter a title for this media"
                />
              </div>

              {usesPixelResolution && availableResolutions ? (
                <div>
                  <Label>Resolution</Label>
                  <Select value={resolution} onValueChange={setResolution}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {availableResolutions.map((r) => (
                        <SelectItem key={r} value={r}>
                          {resolutionLabel(r)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : (
                <div>
                  <Label>Aspect Ratio</Label>
                  <Select value={aspectRatio} onValueChange={setAspectRatio}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {['1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3'].map((r) => (
                        <SelectItem key={r} value={r}>
                          {r}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {outputsVideo && (
                <div>
                  <Label>Duration (seconds)</Label>
                  <Input
                    type="number"
                    min={1}
                    max={30}
                    value={duration}
                    onChange={(e) => setDuration(Number(e.target.value))}
                  />
                </div>
              )}

              {acceptsImage && (
                <div className="space-y-2">
                  <Label>
                    {imageRequired
                      ? 'Reference Image *'
                      : acceptsText
                        ? 'Reference Image (optional)'
                        : 'Reference Image *'}
                  </Label>

                  {!imagePreview ? (
                    <>
                      <button
                        type="button"
                        onClick={() => setShowAssetPicker(true)}
                        className="w-full flex items-center justify-center gap-2 rounded-lg border-2 border-dashed border-muted-foreground/25 p-6 text-sm text-muted-foreground hover:border-primary/50 hover:text-primary transition-colors"
                      >
                        <ImageIcon className="h-5 w-5" />
                        Choose from Media Library
                      </button>

                      <div
                        onDrop={handleFileDrop}
                        onDragOver={handleDragOver}
                        className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-muted-foreground/25 p-6 text-sm text-muted-foreground hover:border-primary/50 hover:text-primary transition-colors cursor-pointer"
                        onClick={() => fileInputRef.current?.click()}
                      >
                        {isUploading ? (
                          <Loader2 className="h-5 w-5 animate-spin" />
                        ) : (
                          <Upload className="h-5 w-5" />
                        )}
                        <span>
                          {isUploading ? 'Uploading...' : 'Drop an image here or click to browse'}
                        </span>
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept="image/*"
                          onChange={handleFileInput}
                          className="hidden"
                        />
                      </div>
                    </>
                  ) : (
                    <div className="relative rounded-lg overflow-hidden border max-h-40">
                      <img
                        src={imagePreview}
                        alt="Reference preview"
                        className="w-full h-40 object-cover"
                      />
                      <button
                        type="button"
                        onClick={resetImage}
                        className="absolute top-1 right-1 rounded-full bg-background/80 p-1 text-foreground hover:bg-background transition-colors"
                        title="Remove reference image"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  )}

                  {imageRequired && !imageAsset && !imageFile && (
                    <p className="text-xs text-destructive">
                      Image is required for this model
                    </p>
                  )}
                </div>
              )}

              {promptRequired && (
                <>
                  <div>
                    <Label>Negative Prompt (optional)</Label>
                    <Input
                      value={negativePrompt}
                      onChange={(e) => setNegativePrompt(e.target.value)}
                      placeholder="Things to avoid..."
                    />
                  </div>

                  <div>
                    <Label>Seed (optional, -1 = random)</Label>
                    <Input
                      value={seed}
                      onChange={(e) => setSeed(e.target.value)}
                      placeholder="-1"
                    />
                  </div>

                  <div>
                    <Label>
                      Prompt{imageRequired ? ' (optional)' : ' *'}
                    </Label>
                    <Textarea
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      placeholder={
                        imageRequired
                          ? 'Additional prompt guidance...'
                          : 'Describe what you want to generate...'
                      }
                      rows={4}
                    />
                  </div>
                </>
              )}

              {estimatedCost && (
                <div className="border-t pt-3 mt-4">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Estimated cost:</span>
                    <span className="font-medium">{estimatedCost}</span>
                  </div>
                </div>
              )}

              <Button
                onClick={handleGenerate}
                disabled={
                  submitting ||
                  isUploading ||
                  (imageRequired && !imageAsset && !imageFile) ||
                  (promptRequired && !prompt.trim()) ||
                  !selectedModel
                }
                className="w-full"
              >
                {submitting && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                Generate
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
