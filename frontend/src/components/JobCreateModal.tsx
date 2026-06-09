import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Upload, Loader2, ChevronDown, ChevronRight, Plus, Search, User } from 'lucide-react'
import api, { jobsApi, templatesApi, modelsApi, type CreateJobRequest, type Template } from '../api/client'
import { projectsApi } from '../api/projects'
import { avatarsApi, type Avatar, type ConsistencyStrategy, type JobAvatarAssignment } from '../api/avatars'
import type { Project } from '../api/types/project'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Badge } from '../components/ui/badge'

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

interface ModelOption {
  id: string
  name: string
  provider: string
  description?: string
}

export default function JobCreateModal({ onClose }: JobCreateModalProps) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [inputValues, setInputValues] = useState<Record<string, unknown>>({})
  const [uploadedFiles, setUploadedFiles] = useState<Record<string, string>>({})
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [isCreatingProject, setIsCreatingProject] = useState(false)
  const [newProjectTitle, setNewProjectTitle] = useState('')
  const [newProjectDescription, setNewProjectDescription] = useState('')

  // Per-job model selections
  const [selectedTextModel, setSelectedTextModel] = useState('')
  const [selectedImageModel, setSelectedImageModel] = useState('')
  const [selectedVideoModel, setSelectedVideoModel] = useState('')
  const [modelsInitialized, setModelsInitialized] = useState(false)

  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({})

  const [selectedAvatars, setSelectedAvatars] = useState<JobAvatarAssignment[]>([])
  const [avatarSectionOpen, setAvatarSectionOpen] = useState(false)
  const [avatarSearchQuery, setAvatarSearchQuery] = useState('')

  const { data: templates, isLoading: templatesLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => templatesApi.list(),
  })

  const { data: availableModels } = useQuery({
    queryKey: ['availableModels'],
    queryFn: () => modelsApi.getAvailableModels(),
  })

  const { data: modelPreferences } = useQuery({
    queryKey: ['modelPreferences'],
    queryFn: () => modelsApi.getModelPreferences(),
  })

  const { data: projects } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list(),
  })

  const { data: avatarList } = useQuery({
    queryKey: ['avatars'],
    queryFn: () => avatarsApi.list(),
  })

  useEffect(() => {
    if (modelsInitialized || !availableModels || !modelPreferences) return
    const findById = (models: { id: string }[] | undefined, id: string) =>
      models?.find((m) => m.id === id)?.id || models?.[0]?.id || ''
    setSelectedVideoModel(findById(
      availableModels.video_models,
      modelPreferences.image_to_video_model || modelPreferences.video_model || '',
    ))
    setSelectedImageModel(findById(
      availableModels.image_models,
      modelPreferences.text_to_image_model || modelPreferences.image_model || '',
    ))
    setSelectedTextModel(findById(
      availableModels.text_models,
      modelPreferences.text_model || '',
    ))
    setModelsInitialized(true)
  }, [availableModels, modelPreferences, modelsInitialized])

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
      setValidationErrors({})
    }
  }, [selectedTemplateId, templateInputs])

  const createMutation = useMutation({
    mutationFn: (data: CreateJobRequest) => jobsApi.create(data),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      const workflowType = selectedTemplate?.config?.workflow_type
      if (workflowType === 'scene_based') {
        navigate(`/editor/${job.id}`)
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
    setValidationErrors((prev) => {
      if (!prev[name]) return prev
      const next = { ...prev }
      delete next[name]
      return next
    })
  }

  const handleFileUpload = async (name: string, file: File, type: string) => {
    const result = await uploadMutation.mutateAsync({ file, type })
    setUploadedFiles((prev) => ({ ...prev, [name]: result.path }))
    setInputValues((prev) => ({ ...prev, [name]: result.path }))
  }

  const filteredAvatars = (avatarList?.avatars || []).filter(
    (a) =>
      !selectedAvatars.some((sa) => sa.avatarId === a.id) &&
      a.name.toLowerCase().includes(avatarSearchQuery.toLowerCase())
  )

  const addAvatar = (avatar: Avatar) => {
    setSelectedAvatars((prev) => [...prev, { avatarId: avatar.id, role: '' }])
    setAvatarSearchQuery('')
  }

  const removeAvatar = (avatarId: string) => {
    setSelectedAvatars((prev) => prev.filter((a) => a.avatarId !== avatarId))
  }

  const updateAvatarRole = (avatarId: string, role: string) => {
    setSelectedAvatars((prev) => prev.map((a) => (a.avatarId === avatarId ? { ...a, role } : a)))
  }

  const updateAvatarOverride = (avatarId: string, strategy: ConsistencyStrategy | '') => {
    setSelectedAvatars((prev) =>
      prev.map((a) =>
        a.avatarId === avatarId
          ? { ...a, consistencyStrategyOverride: strategy || undefined }
          : a
      )
    )
  }

  const validateInputs = (): boolean => {
    const errors: Record<string, string> = {}
    for (const input of templateInputs) {
      const value = inputValues[input.name]
      if (input.required) {
        if (input.type === 'text' && (!value || (value as string).trim() === '')) {
          errors[input.name] = `${input.name} is required.`
          continue
        }
        if (input.type === 'file' && !uploadedFiles[input.name]) {
          errors[input.name] = `${input.name} is required.`
          continue
        }
        if (input.type === 'number' && (value === undefined || value === null || value === '')) {
          errors[input.name] = `${input.name} is required.`
          continue
        }
      }
      if (input.type === 'number' && value !== undefined && value !== null && value !== '') {
        const num = Number(value)
        if (isNaN(num)) {
          errors[input.name] = `${input.name} must be a number.`
        } else if (input.min !== undefined && num < input.min) {
          errors[input.name] = input.max !== undefined
            ? `Must be between ${input.min} and ${input.max}.`
            : `Must be at least ${input.min}.`
        } else if (input.max !== undefined && num > input.max) {
          errors[input.name] = input.min !== undefined
            ? `Must be between ${input.min} and ${input.max}.`
            : `Must be at most ${input.max}.`
        }
      }
    }
    setValidationErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSubmit = () => {
    if (!title.trim()) return
    if (!validateInputs()) return
    createMutation.mutate({
      title: title.trim(),
      template_id: selectedTemplateId || undefined,
      project_id: selectedProjectId || undefined,
      input_data: {
        ...inputValues,
        ...uploadedFiles,
        text_model: selectedTextModel,
        image_model: selectedImageModel,
        video_model: selectedVideoModel,
        avatars: selectedAvatars.map((a) => ({
          avatar_id: a.avatarId,
          role: a.role,
          consistency_strategy_override: a.consistencyStrategyOverride,
        })),
      },
    })
  }

  const renderInput = (input: TemplateInput) => {
    const value = inputValues[input.name]

    switch (input.type) {
      case 'text':
        return (
          <>
            <textarea
              id={input.name}
              className={`flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm${validationErrors[input.name] ? ' border-destructive' : ''}`}
              value={(value as string) || ''}
              onChange={(e) => handleInputChange(input.name, e.target.value)}
              placeholder={input.description}
            />
            {validationErrors[input.name] && (
              <p className="text-xs text-destructive mt-1">{validationErrors[input.name]}</p>
            )}
          </>
        )

      case 'number':
        return (
          <>
            <Input
              type="number"
              id={input.name}
              className={validationErrors[input.name] ? 'border-destructive' : ''}
              value={(value as number) ?? ''}
              onChange={(e) => {
                const raw = e.target.value
                handleInputChange(input.name, raw === '' ? '' : parseFloat(raw))
              }}
              min={input.min}
              max={input.max}
            />
            {(input.min !== undefined || input.max !== undefined) && (
              <p className="text-xs text-muted-foreground mt-1">
                {input.min !== undefined && input.max !== undefined
                  ? `Allowed range: ${input.min} – ${input.max}`
                  : input.min !== undefined
                  ? `Minimum: ${input.min}`
                  : `Maximum: ${input.max}`}
              </p>
            )}
            {validationErrors[input.name] && (
              <p className="text-xs text-destructive mt-1">{validationErrors[input.name]}</p>
            )}
          </>
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
            {validationErrors[input.name] && (
              <p className="text-xs text-destructive mt-1">{validationErrors[input.name]}</p>
            )}
          </div>
        )

      default:
        return null
    }
  }

  // Check if model capabilities include any of the given keys.
  // Handles both object format (Record<string, boolean>) and array format (string[]).
  const hasCapability = (
    capabilities: Record<string, boolean> | string[] | undefined,
    ...keys: string[]
  ): boolean => {
    if (!capabilities) return false
    if (Array.isArray(capabilities)) {
      return keys.some((k) => capabilities.includes(k))
    }
    return keys.some((k) => capabilities[k] === true)
  }

  const renderModelSelect = (
    label: string,
    models: ModelOption[] | undefined,
    selected: string,
    onChange: (id: string) => void,
  ) => (
    <div className="space-y-2">
      <Label>{label}</Label>
      <select
        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
        value={selected}
        onChange={(e) => onChange(e.target.value)}
        disabled={!models?.length}
      >
        {!models?.length && <option value="">Loading...</option>}
        {models?.map((m) => (
          <option key={m.id} value={m.id}>
            {m.name} ({m.provider === 'local' ? 'Local' : 'Cloud'})
          </option>
        ))}
      </select>
    </div>
  )

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
            <Label>Video Title <span className="text-destructive">*</span></Label>
            <Input
              placeholder="Enter a title for your video"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
            />
          </div>

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
                <Button type="button" variant="outline" onClick={() => setIsCreatingProject(true)}>
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
                  <Button type="button" variant="ghost" onClick={() => { setIsCreatingProject(false); setNewProjectTitle(''); setNewProjectDescription('') }}>
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
              <p className="text-sm text-muted-foreground">{selectedTemplate.description}</p>
            )}
          </div>

          {/* AI Model Selection */}
          <div className="space-y-4 border rounded-lg p-4 bg-muted/30">
            <h3 className="text-sm font-semibold text-muted-foreground">AI Models</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {renderModelSelect(
                'Text Model',
                availableModels?.text_models,
                selectedTextModel,
                setSelectedTextModel,
              )}
              {renderModelSelect(
                'Image Model',
                availableModels?.image_models?.filter((m) =>
                  hasCapability(m.capabilities, 'text-to-image', 'accepts_text'),
                ),
                selectedImageModel,
                setSelectedImageModel,
              )}
              {renderModelSelect(
                'Video Model',
                availableModels?.video_models?.filter((m) =>
                  hasCapability(m.capabilities, 'image-to-video', 'accepts_image'),
                ),
                selectedVideoModel,
                setSelectedVideoModel,
              )}
            </div>
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
                  {input.description && input.type !== 'boolean' && input.type !== 'number' && (
                    <p className="text-xs text-muted-foreground">{input.description}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {(avatarList?.avatars?.length ?? 0) > 0 && (
            <div className="space-y-3 border rounded-lg p-4 bg-muted/30">
              <button
                type="button"
                className="flex items-center gap-2 w-full text-left"
                onClick={() => setAvatarSectionOpen(!avatarSectionOpen)}
              >
                {avatarSectionOpen ? (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                )}
                <h3 className="font-medium">Character Cast (Optional)</h3>
                {selectedAvatars.length > 0 && (
                  <Badge variant="secondary" className="ml-1 text-xs">
                    {selectedAvatars.length}
                  </Badge>
                )}
              </button>

              {!avatarSectionOpen && selectedAvatars.length > 0 && (
                <p className="text-xs text-muted-foreground pl-6">
                  {selectedAvatars
                    .map((sa) => {
                      const a = avatarList?.avatars.find((av) => av.id === sa.avatarId)
                      return a?.name || 'Unknown'
                    })
                    .join(', ')}
                </p>
              )}

              {avatarSectionOpen && (
                <div className="space-y-3 pt-1">
                  {selectedAvatars.map((sa) => {
                    const avatar = avatarList?.avatars.find((a) => a.id === sa.avatarId)
                    const thumbnail = avatar?.images?.find((img) => img.isPrimary)?.thumbnailUrl
                    return (
                      <div
                        key={sa.avatarId}
                        className="flex items-center gap-3 p-2 rounded-md border bg-background"
                      >
                        {thumbnail ? (
                          <img
                            src={thumbnail}
                            alt={avatar?.name || ''}
                            className="h-8 w-8 rounded-full object-cover flex-shrink-0"
                          />
                        ) : (
                          <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center flex-shrink-0">
                            <User className="h-4 w-4 text-muted-foreground" />
                          </div>
                        )}
                        <span className="text-sm font-medium w-24 flex-shrink-0 truncate">
                          {avatar?.name || 'Unknown'}
                        </span>
                        <Input
                          className="h-8 text-xs flex-1 min-w-0"
                          placeholder="Role (e.g. narrator, hero)"
                          value={sa.role || ''}
                          onChange={(e) => updateAvatarRole(sa.avatarId, e.target.value)}
                        />
                        <select
                          className="h-8 rounded-md border border-input bg-background px-2 text-xs flex-shrink-0"
                          value={sa.consistencyStrategyOverride || ''}
                          onChange={(e) =>
                            updateAvatarOverride(
                              sa.avatarId,
                              e.target.value as ConsistencyStrategy | ''
                            )
                          }
                          title="Consistency override"
                        >
                          <option value="">Default strategy</option>
                          <option value="ip_adapter">IP-Adapter</option>
                          <option value="face_swap">Face Swap</option>
                          <option value="lora">LoRA</option>
                          <option value="prompt_only">Prompt Only</option>
                        </select>
                        <button
                          type="button"
                          className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-destructive flex-shrink-0"
                          onClick={() => removeAvatar(sa.avatarId)}
                          title="Remove avatar"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    )
                  })}

                  <div className="relative">
                    <div className="flex gap-2">
                      <div className="relative flex-1">
                        <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                          className="h-9 pl-8 text-sm"
                          placeholder="Search avatars..."
                          value={avatarSearchQuery}
                          onChange={(e) => setAvatarSearchQuery(e.target.value)}
                        />
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-9 flex-shrink-0"
                        disabled={filteredAvatars.length === 0}
                        onClick={() => {
                          if (filteredAvatars.length > 0) addAvatar(filteredAvatars[0])
                        }}
                      >
                        <Plus className="h-4 w-4 mr-1" />
                        Add
                      </Button>
                    </div>
                    {avatarSearchQuery && filteredAvatars.length > 0 && (
                      <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-md max-h-48 overflow-y-auto">
                        {filteredAvatars.map((avatar) => {
                          const thumbnail = avatar.images?.find((img) => img.isPrimary)?.thumbnailUrl
                          return (
                            <button
                              key={avatar.id}
                              type="button"
                              className="flex items-center gap-3 w-full px-3 py-2 text-sm hover:bg-accent text-left"
                              onClick={() => addAvatar(avatar)}
                            >
                              {thumbnail ? (
                                <img
                                  src={thumbnail}
                                  alt={avatar.name}
                                  className="h-6 w-6 rounded-full object-cover"
                                />
                              ) : (
                                <User className="h-5 w-5 text-muted-foreground" />
                              )}
                              <div className="flex-1 min-w-0">
                                <div className="truncate">{avatar.name}</div>
                                <div className="text-xs text-muted-foreground">
                                  {avatar.gender}
                                  {avatar.jobCount > 0 ? ` · ${avatar.jobCount} jobs` : ''}
                                </div>
                              </div>
                            </button>
                          )
                        })}
                      </div>
                    )}
                    {avatarSearchQuery && filteredAvatars.length === 0 && (
                      <p className="text-xs text-muted-foreground mt-1">No matching avatars</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 p-6 border-t bg-secondary/50">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={createMutation.isPending || !selectedTemplateId || !title.trim()}
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
