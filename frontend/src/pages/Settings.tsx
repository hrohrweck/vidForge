import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, RefreshCw, Trash2, Folder, File, Sun, Moon, Monitor, Cpu } from 'lucide-react'
import { storageApi, stylesApi, modelsApi, type ModelConfig, type ModelPreferences } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Badge } from '../components/ui/badge'

export default function Settings() {
  const { user } = useAuthStore()
  const { theme, setTheme } = useThemeStore()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<'account' | 'appearance' | 'storage' | 'styles' | 'models'>('account')
  
  const [storageSettings, setStorageSettings] = useState({
    default_style: '',
    storage_backend: 'local',
    s3_endpoint: '',
    s3_bucket: '',
    s3_access_key: '',
    s3_secret_key: '',
    ssh_host: '',
    ssh_user: '',
    ssh_remote_path: '',
  })

  const { data: storageConfig, isLoading: configLoading } = useQuery({
    queryKey: ['storage-config'],
    queryFn: () => storageApi.getConfig(),
  })

  const { data: styles } = useQuery({
    queryKey: ['styles'],
    queryFn: () => stylesApi.list(),
  })

  const { data: files, isLoading: filesLoading, refetch: refetchFiles } = useQuery({
    queryKey: ['storage-files'],
    queryFn: () => storageApi.listFiles(''),
    enabled: activeTab === 'storage',
  })

  const { data: availableModels } = useQuery({
    queryKey: ['available-models'],
    queryFn: () => modelsApi.getAvailableModels(),
    enabled: activeTab === 'models',
  })

  const { data: modelPreferences } = useQuery({
    queryKey: ['model-preferences'],
    queryFn: () => modelsApi.getModelPreferences(),
    enabled: activeTab === 'models',
  })

  const updateModelPreferencesMutation = useMutation({
    mutationFn: modelsApi.updateModelPreferences,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['model-preferences'] })
    },
  })

  const allModels: ModelConfig[] = useMemo(() => {
    if (!availableModels) return []
    return [
      ...(availableModels.image_models || []),
      ...(availableModels.video_models || []),
      ...(availableModels.text_models || []),
    ]
  }, [availableModels])

  const textToImageModels = useMemo(() =>
    allModels.filter(m => m.capabilities?.accepts_text && m.capabilities?.outputs_image),
    [allModels]
  )
  const imageToImageModels = useMemo(() =>
    allModels.filter(m => m.capabilities?.accepts_image && m.capabilities?.outputs_image),
    [allModels]
  )
  const textToVideoModels = useMemo(() =>
    allModels.filter(m => m.capabilities?.accepts_text && m.capabilities?.outputs_video),
    [allModels]
  )
  const imageToVideoModels = useMemo(() =>
    allModels.filter(m => m.capabilities?.accepts_image && m.capabilities?.outputs_video),
    [allModels]
  )

  const buildPreferences = (overrides: Partial<ModelPreferences>): ModelPreferences => ({
    image_model: modelPreferences?.image_model || 'flux1-schnell',
    video_model: modelPreferences?.video_model || 'wan2.2',
    text_model: modelPreferences?.text_model || 'qwen3.6:35b',
    image_provider: modelPreferences?.image_provider || 'local',
    video_provider: modelPreferences?.video_provider || 'local',
    text_provider: modelPreferences?.text_provider || 'local',
    text_to_image_model: modelPreferences?.text_to_image_model || 'flux1-schnell',
    image_to_image_model: modelPreferences?.image_to_image_model || 'flux1-schnell',
    text_to_video_model: modelPreferences?.text_to_video_model || 'wan2.2',
    image_to_video_model: modelPreferences?.image_to_video_model || 'wan2.2',
    ...overrides,
  })

  const updateSettingsMutation = useMutation({
    mutationFn: async (settings: typeof storageSettings & { preferences?: { auto_create_jobs: boolean } }) => {
      const response = await fetch('/api/users/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      })
      if (!response.ok) throw new Error('Failed to update settings')
      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['storage-config'] })
    },
  })

  const deleteFileMutation = useMutation({
    mutationFn: (path: string) => storageApi.deleteFile(path),
    onSuccess: () => {
      refetchFiles()
    },
  })

  const [autoCreateJobs, setAutoCreateJobs] = useState(false)

  const handleSaveSettings = () => {
    updateSettingsMutation.mutate({
      ...storageSettings,
      preferences: { auto_create_jobs: autoCreateJobs },
    })
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleString()
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-muted-foreground">Manage your account and preferences</p>
      </div>

      <div className="flex gap-2 border-b">
        {(['account', 'appearance', 'storage', 'styles', 'models'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
              activeTab === tab
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {tab === 'models' ? 'AI Models' : tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {activeTab === 'account' && (
        <div className="space-y-6">
          <div className="border rounded-lg p-6">
            <h2 className="text-lg font-semibold mb-4">Account Information</h2>
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label>Email</Label>
                  <p className="text-sm mt-1">{user?.email}</p>
                </div>
                <div>
                  <Label>Status</Label>
                  <p className="text-sm mt-1">
                    <Badge variant={user?.is_active ? 'outline' : 'destructive'}>
                      {user?.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="border rounded-lg p-6">
            <h2 className="text-lg font-semibold mb-4">Preferences</h2>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="default_style">Default Style</Label>
                <select
                  id="default_style"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={storageSettings.default_style}
                  onChange={(e) =>
                    setStorageSettings({ ...storageSettings, default_style: e.target.value })
                  }
                >
                  <option value="">None</option>
                  {styles?.data?.map((style) => (
                    <option key={style.id} value={style.id}>
                      {style.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="auto_create_jobs"
                  checked={autoCreateJobs}
                  onChange={(e) => setAutoCreateJobs(e.target.checked)}
                  className="h-4 w-4 rounded border-input"
                />
                <div>
                  <Label htmlFor="auto_create_jobs">Auto-create jobs without confirmation</Label>
                  <p className="text-xs text-muted-foreground">
                    When enabled, jobs are created immediately without asking for confirmation
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'appearance' && (
        <div className="border rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Appearance</h2>
          <p className="text-sm text-muted-foreground mb-4">
            Choose how VidForge looks to you.
          </p>
          <div className="space-y-2">
            {(['light', 'dark', 'system'] as const).map((option) => (
              <label
                key={option}
                className={`flex items-center gap-3 p-3 border rounded-lg cursor-pointer transition ${
                  theme === option ? 'bg-secondary' : 'hover:bg-muted/50'
                }`}
                onClick={() => setTheme(option)}
              >
                <div className="flex items-center gap-3">
                  {option === 'light' && <Sun className="h-5 w-5 text-primary" />}
                  {option === 'dark' && <Moon className="h-5 w-5 text-primary" />}
                  {option === 'system' && <Monitor className="h-5 w-5 text-muted-foreground" />}
                  <div>
                    <p className="font-medium">{option.charAt(0).toUpperCase() + option.slice(1)}</p>
                    <p className="text-xs text-muted-foreground">
                      {option === 'light' && 'Always use light mode'}
                      {option === 'dark' && 'Always use dark mode'}
                      {option === 'system' && 'Follow your system preference'}
                    </p>
                  </div>
                </div>
              </label>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'storage' && (
        <div className="space-y-6">
          <div className="border rounded-lg p-6">
            <h2 className="text-lg font-semibold mb-4">Storage Configuration</h2>
            {configLoading ? (
              <div className="flex items-center justify-center py-4">
                <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>Current Backend</Label>
                  <p className="text-sm mt-1 capitalize">{storageConfig?.data?.backend}</p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="storage_backend">Preferred Storage Backend</Label>
                  <select
                    id="storage_backend"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    value={storageSettings.storage_backend}
                    onChange={(e) =>
                      setStorageSettings({ ...storageSettings, storage_backend: e.target.value })
                    }
                  >
                    <option value="local">Local Storage</option>
                    <option value="s3">S3 Compatible</option>
                    <option value="ssh">SSH/SFTP</option>
                  </select>
                </div>

                {storageSettings.storage_backend === 's3' && (
                  <div className="space-y-4 pt-4 border-t">
                    <h3 className="font-medium">S3 Configuration</h3>
                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="space-y-2">
                        <Label htmlFor="s3_endpoint">Endpoint</Label>
                        <Input
                          id="s3_endpoint"
                          value={storageSettings.s3_endpoint}
                          onChange={(e) =>
                            setStorageSettings({ ...storageSettings, s3_endpoint: e.target.value })
                          }
                          placeholder="https://s3.amazonaws.com"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="s3_bucket">Bucket</Label>
                        <Input
                          id="s3_bucket"
                          value={storageSettings.s3_bucket}
                          onChange={(e) =>
                            setStorageSettings({ ...storageSettings, s3_bucket: e.target.value })
                          }
                          placeholder="my-bucket"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="s3_access_key">Access Key</Label>
                        <Input
                          id="s3_access_key"
                          type="password"
                          value={storageSettings.s3_access_key}
                          onChange={(e) =>
                            setStorageSettings({
                              ...storageSettings,
                              s3_access_key: e.target.value,
                            })
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="s3_secret_key">Secret Key</Label>
                        <Input
                          id="s3_secret_key"
                          type="password"
                          value={storageSettings.s3_secret_key}
                          onChange={(e) =>
                            setStorageSettings({
                              ...storageSettings,
                              s3_secret_key: e.target.value,
                            })
                          }
                        />
                      </div>
                    </div>
                  </div>
                )}

                {storageSettings.storage_backend === 'ssh' && (
                  <div className="space-y-4 pt-4 border-t">
                    <h3 className="font-medium">SSH Configuration</h3>
                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="space-y-2">
                        <Label htmlFor="ssh_host">Host</Label>
                        <Input
                          id="ssh_host"
                          value={storageSettings.ssh_host}
                          onChange={(e) =>
                            setStorageSettings({ ...storageSettings, ssh_host: e.target.value })
                          }
                          placeholder="server.example.com"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="ssh_user">User</Label>
                        <Input
                          id="ssh_user"
                          value={storageSettings.ssh_user}
                          onChange={(e) =>
                            setStorageSettings({ ...storageSettings, ssh_user: e.target.value })
                          }
                          placeholder="username"
                        />
                      </div>
                      <div className="space-y-2 md:col-span-2">
                        <Label htmlFor="ssh_remote_path">Remote Path</Label>
                        <Input
                          id="ssh_remote_path"
                          value={storageSettings.ssh_remote_path}
                          onChange={(e) =>
                            setStorageSettings({
                              ...storageSettings,
                              ssh_remote_path: e.target.value,
                            })
                          }
                          placeholder="/var/lib/vidforge/storage"
                        />
                      </div>
                    </div>
                  </div>
                )}

                <div className="flex justify-end pt-4">
                  <Button
                    onClick={handleSaveSettings}
                    disabled={updateSettingsMutation.isPending}
                  >
                    <Save className="h-4 w-4 mr-2" />
                    Save Settings
                  </Button>
                </div>
              </div>
            )}
          </div>

          <div className="border rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">My Files</h2>
              <Button variant="outline" size="sm" onClick={() => refetchFiles()}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh
              </Button>
            </div>

            {filesLoading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : files?.data?.files && files.data.files.length > 0 ? (
              <div className="border rounded-lg divide-y">
                {files.data.files.map((file: any, index: number) => (
                  <div
                    key={index}
                    className="p-3 flex items-center justify-between hover:bg-muted/50"
                  >
                    <div className="flex items-center gap-3">
                      {file.path.endsWith('/') ? (
                        <Folder className="h-5 w-5 text-primary" />
                      ) : (
                        <File className="h-5 w-5 text-muted-foreground" />
                      )}
                      <div>
                        <p className="text-sm font-medium">{file.path.split('/').pop()}</p>
                        <p className="text-xs text-muted-foreground">
                          {formatFileSize(file.size)} • {formatDate(file.modified)}
                        </p>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => deleteFileMutation.mutate(file.path)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center text-muted-foreground py-8">No files uploaded yet</p>
            )}
          </div>
        </div>
      )}

      {activeTab === 'styles' && (
        <div className="border rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Available Styles</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {styles?.data?.map((style) => (
              <div
                key={style.id}
                className="p-4 bg-secondary rounded-lg hover:bg-secondary/80 transition"
              >
                <p className="font-medium">{style.name}</p>
                {style.category && (
                  <p className="text-xs text-muted-foreground mt-1">{style.category}</p>
                )}
                {style.params && Object.keys(style.params).length > 0 && (
                  <div className="mt-2 pt-2 border-t border-border">
                    <p className="text-xs text-muted-foreground">Parameters:</p>
                    <ul className="text-xs mt-1 space-y-1">
                      {Object.entries(style.params).slice(0, 3).map(([key, value]) => (
                        <li key={key} className="truncate">
                          {key}: {String(value)}
                        </li>
                      ))}
                      {Object.keys(style.params).length > 3 && (
                        <li className="text-muted-foreground">
                          +{Object.keys(style.params).length - 3} more
                        </li>
                      )}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'models' && (
        <div className="space-y-6">
          <div className="border rounded-lg p-6">
            <div className="flex items-center gap-2 mb-4">
              <Cpu className="h-5 w-5" />
              <h2 className="text-lg font-semibold">AI Model Preferences</h2>
            </div>
            <p className="text-sm text-muted-foreground mb-6">
              Choose which AI models to use for each generation category. Only compatible models are shown based on their capabilities.
            </p>

            <div className="space-y-8">
              {/* Text-to-Image */}
              <div className="space-y-2">
                <Label htmlFor="text-to-image">Text-to-Image</Label>
                <p className="text-xs text-muted-foreground">Generate images from text prompts</p>
                <select
                  id="text-to-image"
                  className="flex h-10 w-full max-w-md rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={modelPreferences?.text_to_image_model || 'flux1-schnell'}
                  onChange={(e) =>
                    updateModelPreferencesMutation.mutate(
                      buildPreferences({ text_to_image_model: e.target.value })
                    )
                  }
                >
                  {textToImageModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name} ({model.provider})
                    </option>
                  ))}
                  {textToImageModels.length === 0 && (
                    <option value="" disabled>No compatible models available</option>
                  )}
                </select>
              </div>

              {/* Image-to-Image */}
              <div className="space-y-2">
                <Label htmlFor="image-to-image">Image-to-Image</Label>
                <p className="text-xs text-muted-foreground">Transform or enhance existing images</p>
                <select
                  id="image-to-image"
                  className="flex h-10 w-full max-w-md rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={modelPreferences?.image_to_image_model || 'flux1-schnell'}
                  onChange={(e) =>
                    updateModelPreferencesMutation.mutate(
                      buildPreferences({ image_to_image_model: e.target.value })
                    )
                  }
                >
                  {imageToImageModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name} ({model.provider})
                    </option>
                  ))}
                  {imageToImageModels.length === 0 && (
                    <option value="" disabled>No compatible models available</option>
                  )}
                </select>
              </div>

              {/* Text-to-Video */}
              <div className="space-y-2">
                <Label htmlFor="text-to-video">Text-to-Video</Label>
                <p className="text-xs text-muted-foreground">Generate videos from text prompts</p>
                <select
                  id="text-to-video"
                  className="flex h-10 w-full max-w-md rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={modelPreferences?.text_to_video_model || 'wan2.2'}
                  onChange={(e) =>
                    updateModelPreferencesMutation.mutate(
                      buildPreferences({ text_to_video_model: e.target.value })
                    )
                  }
                >
                  {textToVideoModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name} ({model.provider})
                    </option>
                  ))}
                  {textToVideoModels.length === 0 && (
                    <option value="" disabled>No compatible models available</option>
                  )}
                </select>
              </div>

              {/* Image-to-Video */}
              <div className="space-y-2">
                <Label htmlFor="image-to-video">Image-to-Video</Label>
                <p className="text-xs text-muted-foreground">Animate existing images into videos</p>
                <select
                  id="image-to-video"
                  className="flex h-10 w-full max-w-md rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={modelPreferences?.image_to_video_model || 'wan2.2'}
                  onChange={(e) =>
                    updateModelPreferencesMutation.mutate(
                      buildPreferences({ image_to_video_model: e.target.value })
                    )
                  }
                >
                  {imageToVideoModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name} ({model.provider})
                    </option>
                  ))}
                  {imageToVideoModels.length === 0 && (
                    <option value="" disabled>No compatible models available</option>
                  )}
                </select>
              </div>

              {/* Text Generation */}
              <div className="space-y-4">
                <h3 className="font-medium text-base">Text Generation Model</h3>
                <p className="text-sm text-muted-foreground">Used for story creation, scene planning, prompt enhancement, and lyrics analysis.</p>
                <div className="grid gap-4 md:grid-cols-2">
                  {availableModels?.text_models?.map((model) => (
                    <div
                      key={model.id}
                      className={`p-4 border rounded-lg cursor-pointer transition ${
                        modelPreferences?.text_model === model.id
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:border-primary/50'
                      }`}
                      onClick={() =>
                        updateModelPreferencesMutation.mutate(
                          buildPreferences({ text_model: model.id })
                        )
                      }
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <p className="font-medium">{model.name}</p>
                          <p className="text-sm text-muted-foreground mt-1">{model.description}</p>
                        </div>
                        {model.default && (
                          <Badge variant="outline" className="text-xs">Default</Badge>
                        )}
                      </div>
                      <div className="flex gap-2 mt-3">
                        <Badge variant="secondary" className="text-xs">{model.size_gb}GB</Badge>
                        <Badge variant="secondary" className="text-xs">{model.speed}</Badge>
                        <Badge variant="secondary" className="text-xs">{model.quality}</Badge>
                        {model.provider === 'local' ? (
                          <Badge variant="outline" className="text-xs text-green-600">Local</Badge>
                        ) : (
                          <Badge variant="outline" className="text-xs text-blue-600">Cloud</Badge>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
