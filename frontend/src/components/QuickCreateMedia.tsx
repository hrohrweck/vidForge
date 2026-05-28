import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Loader2 } from 'lucide-react'
import api, { modelsApi, type ModelConfig } from '../api/client'
import { Button } from './ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog'
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

interface ModelOption {
  id: string
  name: string
  provider: string
  description?: string
}

export interface QuickCreateMediaProps {
  triggerClassName?: string
  onSuccess?: () => void
}

function toModelOption(m: ModelConfig): ModelOption {
  return {
    id: m.id,
    name: m.name,
    provider: m.provider,
    description: m.description,
  }
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
  const [submitting, setSubmitting] = useState(false)

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

  const handleModelSelect = (model: ModelOption) => {
    setSelectedModel(model)
    setStep('configure')
  }

  const handleGenerate = async () => {
    if (!prompt.trim() || !selectedModel) return
    setSubmitting(true)
    try {
      await api.post('/api/media/generate', {
        model_id: selectedModel.id,
        prompt: prompt.trim(),
        aspect_ratio: aspectRatio,
        duration: duration,
        negative_prompt: negativePrompt || undefined,
        seed: seed ? Number(seed) : undefined,
      })
      setOpen(false)
      setStep('select')
      setPrompt('')
      onSuccess?.()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <Button onClick={() => setOpen(true)} className={triggerClassName}>
        <Plus className="h-4 w-4 mr-2" />
        Create Media
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Create Media</DialogTitle>
          </DialogHeader>
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : step === 'select' ? (
            <Tabs defaultValue="image">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="image">Image Models</TabsTrigger>
                <TabsTrigger value="video">Video Models</TabsTrigger>
              </TabsList>
              <TabsContent value="image" className="space-y-2 mt-4 max-h-64 overflow-y-auto">
                {imageModels.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-8 text-center">
                    No image models available
                  </p>
                ) : (
                  imageModels.map((m) => (
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
                {videoModels.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-8 text-center">
                    No video models available
                  </p>
                ) : (
                  videoModels.map((m) => (
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
          ) : (
            <div className="space-y-4">
              <button
                onClick={() => setStep('select')}
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                &larr; Back to model selection
              </button>
              <div className="font-medium">{selectedModel?.name}</div>

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

              {selectedModel && selectedModel.provider === 'video' && (
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
                <Label>Prompt *</Label>
                <Textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Describe what you want to generate..."
                  rows={4}
                />
              </div>

              <Button
                onClick={handleGenerate}
                disabled={!prompt.trim() || submitting}
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
