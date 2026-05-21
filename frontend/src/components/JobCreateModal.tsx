import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Upload, Loader2 } from 'lucide-react'
import api, { jobsApi, templatesApi, providersApi, type CreateJobRequest, type Template, type Provider } from '../api/client'
import { projectsApi } from '../api/projects'
import type { Project } from '../api/types/project'
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
  const navigate = useNavigate()
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [inputValues, setInputValues] = useState<Record<string, unknown>>({})
  const [uploadedFiles, setUploadedFiles] = useState<Record<string, string>>({})
  const [providerPreference, setProviderPreference] = useState<string>('auto')
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [isCreatingProject, setIsCreatingProject] = useState(false)
  const [newProjectTitle, setNewProjectTitle] = useState('')
  const [newProjectDescription, setNewProjectDescription] = useState('')

  const { data: templates, isLoading: templatesLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => templatesApi.list(),
  })

  const { data: providers } = useQuery({
    queryKey: ['providers'],
    queryFn: () => providersApi.list(),
  })

  const { data: projects } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list(),
  })

  const activeProviders = providers?.filter((p: Provider) => p.is_active) || []

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
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      const workflowType = selectedTemplate?.config?.workflow_type
      if (workflowType === 'scene_based') {
        navigate(`/editor/music/${job.id}`)
      } else {
        onClose()
      }
    },
  })

  const createProjectMutation = useMutation({
    mutationFn: projectsApi.create,
    onSuccess: (newProject) => {
      setSelectedProjectId(newProject.id)
      setIsCreatingProject(false)
      setNewProjectTitle('')
      setNewProjectDescription('')
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  const uploadMutation = useMutation({
    mutationFn: async ({ file, type }: { file: File; type: string }) => {
      const formData = new FormData()
      formData.append('file', file)
      const response = await api.post(`/uploads/${type}`, formData, {
        headers: {
          'Content-Type': undefined,
        },
      })
      return response.data
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
      project_id: selectedProjectId || undefined,
      input_data: { ...inputValues, ...uploadedFiles },
      provider_preference: providerPreference,
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
              <p className="text-sm text-primary">
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
            <Label>Project</Label>
            {!isCreatingProject ? (
              <div className="flex gap-2">
                <select
                  value={selectedProjectId}
                  onChange={(e) => setSelectedProjectId(e.target.value)}
                  className="flex-1 px-3 py-2 border rounded-md"
                >
                  <option value="">Select a project...</option>
                  {projects?.map((project: Project) => (
                    <option key={project.id} value={project.id}>
                      {project.title}
                    </option>
                  ))}
                </select>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCreatingProject(true)}
                >
                  + New
                </Button>
              </div>
            ) : (
              <div className="space-y-2 p-3 border rounded-md bg-muted/50">
                <Input
                  placeholder="Project title"
                  value={newProjectTitle}
                  onChange={(e) => setNewProjectTitle(e.target.value)}
                />
                <Input
                  placeholder="Description (optional)"
                  value={newProjectDescription}
                  onChange={(e) => setNewProjectDescription(e.target.value)}
                />
                <div className="flex gap-2">
                  <Button
                    type="button"
                    onClick={() => createProjectMutation.mutate({
                      title: newProjectTitle,
                      description: newProjectDescription,
                    })}
                    disabled={!newProjectTitle.trim() || createProjectMutation.isPending}
                  >
                    {createProjectMutation.isPending ? 'Creating...' : 'Create Project'}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setIsCreatingProject(false)
                      setNewProjectTitle('')
                      setNewProjectDescription('')
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </div>

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

          {templateInputs.length > 0 && (
            <div className="space-y-4">
              <h3 className="font-medium">Input Parameters</h3>
              {templateInputs.map((input) => (
                <div key={input.name} className="space-y-2">
                  <Label htmlFor={input.name}>
                    {input.name}
                    {input.required && <span className="text-destructive ml-1">*</span>}
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
