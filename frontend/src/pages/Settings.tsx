import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, RefreshCw, Trash2, Folder, File, Sun, Moon, Monitor } from 'lucide-react'
import { storageApi, stylesApi } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'

export default function Settings() {
  const { user } = useAuthStore()
  const { theme, setTheme } = useThemeStore()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<'account' | 'appearance' | 'storage' | 'styles'>('account')
  
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

  const updateSettingsMutation = useMutation({
    mutationFn: async (settings: typeof storageSettings) => {
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

  const handleSaveSettings = () => {
    updateSettingsMutation.mutate(storageSettings)
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
        {(['account', 'appearance', 'storage', 'styles'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
              activeTab === tab
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
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
                    <span
                      className={`px-2 py-1 rounded text-xs ${
                        user?.is_active
                          ? 'bg-green-100 text-green-800'
                          : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {user?.is_active ? 'Active' : 'Inactive'}
                    </span>
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
                  theme === option ? 'bg-secondary' : 'hover:bg-gray-50'
                }`}
                onClick={() => setTheme(option)}
              >
                <div className="flex items-center gap-3">
                  {option === 'light' && <Sun className="h-5 w-5 text-yellow-500" />}
                  {option === 'dark' && <Moon className="h-5 w-5 text-blue-400" />}
                  {option === 'system' && <Monitor className="h-5 w-5 text-gray-500" />}
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
                    className="p-3 flex items-center justify-between hover:bg-gray-50"
                  >
                    <div className="flex items-center gap-3">
                      {file.path.endsWith('/') ? (
                        <Folder className="h-5 w-5 text-blue-500" />
                      ) : (
                        <File className="h-5 w-5 text-gray-500" />
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
    </div>
  )
}
