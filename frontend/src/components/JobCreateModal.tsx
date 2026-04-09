import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Upload, Loader2 } from 'lucide-react'
import { jobsApi, templatesApi, modelsApi, providersApi, type CreateJobRequest, type Template, type VideoModel, type Provider } from '../api/client'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'

interface JobCreateModalProps {
  onClose: () => void
}

interface TemplateInput {
  name: string
  type: 'text' | 'number' | 'select' | 'boolean' | 'file'
  required?: boolean
  default?: string | number | boolean
  description?: string
  options?: string[]
  min?: number
  max?: number
}

export default function JobCreateModal({ onClose }: JobCreateModalProps) {
  const queryClient = useQueryClient()
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [inputValues, setInputValues] = useState<Record<string, unknown>>({})
  const [uploadedFiles, setUploadedFiles] = useState<Record<string, string>>({})
  const [providerPreference, setProviderPreference] = useState<string>('auto')
  const [modelPreference, setModelPreference] = useState<string>('')

  const { data: templates, isLoading: templatesLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => templatesApi.list(),
  })

  const { data: models } = useQuery({
    queryKey: ['models'],
    queryFn: () => modelsApi.list(),
  })

  const { data: providers } = useQuery({
    queryKey: ['providers'],
    queryFn: () => providersApi.list(),
  })

  const activeProviders = providers?.filter((p: Provider) => p.is_active) || []
  
  const selectedProvider = activeProviders.find((p: Provider) => p.id === providerPreference)

  const modelProviderType = selectedProvider ? selectedProvider.provider_type : null
  
  const filteredModels = models?.filter((m: VideoModel) => {
    if (!modelProviderType || modelProviderType === 'poe') return true
    return modelProviderType === 'comfyui_direct' || modelProviderType === 'runpod'
      ? (m.provider === 'wan' || m.provider === 'ltx')
      : true
  }) || []

  const selectedTemplate = templates?.data?.find(
    (t: Template) => t.id === selectedTemplateId
  )

  const templateInputs: TemplateInput[] = (selectedTemplate?.config?.inputs as TemplateInput[]) || []

  useEffect(() => {
    if (templateInputs.length > 0) {
      const defaults: Record<string, unknown> = {}
      templateInputs.forEach((input) => {
        if (input.default !== undefined) {
          defaults[input.name] = input.default
        }
      })
      setInputValues(defaults)
    }
  }, [selectedTemplateId, templateInputs])

  const createMutation = useMutation({
    mutationFn: (data: CreateJobRequest) => jobsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      onClose()
    },
  })

  const uploadMutation = useMutation({
    mutationFn: async ({ file, type }: { file: File; type: string }) => {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch(`/api/uploads/${type}`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) throw new Error('Upload failed')
      return response.json()
    },
  })

  const handleInputChange = (name: string, value: unknown) => {
    setInputValues((prev) => ({ ...prev, [name]: value }))
  }

  const handleFileUpload = async (name: string, file: File, type: string) => {
    const result = await uploadMutation.mutateAsync({ file, type })
    setUploadedFiles((prev) => ({ ...prev, [name]: result.path }))
    setInputValues((prev) => ({ ...prev, [name]: result.path }))
  }

  const handleSubmit = () => {
    createMutation.mutate({
      template_id: selectedTemplateId || undefined,
      input_data: { ...inputValues, ...uploadedFiles },
      provider_preference: providerPreference,
      model_preference: modelPreference || undefined,
    })
  }

  const renderInput = (input: TemplateInput) => {
    const value = inputValues[input.name]

    switch (input.type) {
      case 'text':
        return (
          <textarea
            id={input.name}
            className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={(value as string) || ''}
            onChange={(e) => handleInputChange(input.name, e.target.value)}
            placeholder={input.description}
          />
        )

      case 'number':
        return (
          <Input
            type="number"
            id={input.name}
            value={(value as number) || ''}
            onChange={(e) => handleInputChange(input.name, parseFloat(e.target.value))}
            min={input.min}
            max={input.max}
          />
        )

      case 'select':
        return (
          <select
            id={input.name}
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={(value as string) || ''}
            onChange={(e) => handleInputChange(input.name, e.target.value)}
          >
            {input.options?.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        )

      case 'boolean':
        return (
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={(value as boolean) || false}
              onChange={(e) => handleInputChange(input.name, e.target.checked)}
              className="rounded"
            />
            <span className="text-sm text-muted-foreground">{input.description}</span>
          </label>
        )

      case 'file':
        return (
          <div className="space-y-2">
            <input
              type="file"
              id={input.name}
              accept="audio/*,video/*,image/*"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) {
                  const type = file.type.startsWith('audio/')
                    ? 'audio'
                    : file.type.startsWith('video/')
                    ? 'video'
                    : 'image'
                  handleFileUpload(input.name, file, type)
                }
              }}
              className="hidden"
            />
            <Button
              variant="outline"
              onClick={() => document.getElementById(input.name)?.click()}
              disabled={uploadMutation.isPending}
            >
              <Upload className="h-4 w-4 mr-2" />
              {uploadedFiles[input.name] ? 'Change File' : 'Upload File'}
            </Button>
            {uploadedFiles[input.name] && (
              <p className="text-sm text-green-600">
                Uploaded: {uploadedFiles[input.name]}
              </p>
            )}
          </div>
        )

      default:
        return null
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto border">
        <div className="flex items-center justify-between p-6 border-b">
          <h2 className="text-xl font-semibold">Create New Job</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div className="space-y-2">
            <Label htmlFor="template">Template</Label>
            <select
              id="template"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={selectedTemplateId}
              onChange={(e) => {
                setSelectedTemplateId(e.target.value)
                setInputValues({})
                setUploadedFiles({})
              }}
              disabled={templatesLoading}
            >
              <option value="">Select a template...</option>
              {templates?.data?.map((t: Template) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          {selectedTemplate?.description && (
            <p className="text-sm text-muted-foreground">
              {selectedTemplate.description}
            </p>
          )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="providerPreference">Provider Preference</Label>
            <select
              id="providerPreference"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={providerPreference}
              onChange={(e) => {
                setProviderPreference(e.target.value)
                setModelPreference('')
              }}
            >
              <option value="auto">Auto</option>
              {activeProviders.map((provider: Provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name} ({provider.provider_type})
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="modelPreference">Generation Model</Label>
            <select
              id="modelPreference"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={modelPreference}
              onChange={(e) => setModelPreference(e.target.value)}
            >
              <option value="">Use template default</option>
              {filteredModels.map((model: VideoModel) => (
                <option key={model.id} value={model.id}>
                  {model.display_name} ({model.provider.toUpperCase()})
                  {model.distilled ? ' - Fast' : ''}
                  {model.modality === 'image' ? ' - Image' : ''}
                </option>
              ))}
            </select>
            {modelPreference && (
              <p className="text-xs text-muted-foreground">
                {models?.find((m: VideoModel) => m.id === modelPreference)?.description}
              </p>
            )}
          </div>

          {templateInputs.length > 0 && (
            <div className="space-y-4">
              <h3 className="font-medium">Input Parameters</h3>
              {templateInputs.map((input) => (
                <div key={input.name} className="space-y-2">
                  <Label htmlFor={input.name}>
                    {input.name}
                    {input.required && <span className="text-red-500 ml-1">*</span>}
                  </Label>
                  {renderInput(input)}
                  {input.description && input.type !== 'boolean' && (
                    <p className="text-xs text-muted-foreground">{input.description}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 p-6 border-t bg-secondary/50">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={createMutation.isPending || !selectedTemplateId}
          >
            {createMutation.isPending && (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            )}
            Create Job
          </Button>
        </div>
      </div>
    </div>
  )
}
