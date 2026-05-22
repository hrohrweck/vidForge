import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import { useAuthStore } from '../../stores/auth'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'

interface MediaSettings {
  max_folder_depth: number
}

export function MediaSettingsCard() {
  const queryClient = useQueryClient()
  const { user: adminUser } = useAuthStore()
  const [localValue, setLocalValue] = useState<number>(3)
  const [showSuccess, setShowSuccess] = useState(false)

  const { data: settings, isLoading } = useQuery<MediaSettings>({
    queryKey: ['admin-media-settings'],
    queryFn: async () => {
      const response = await fetch('/api/admin/settings/media', {
        headers: {
          Authorization: `Bearer ${useAuthStore.getState().token}`,
        },
      })
      if (!response.ok) throw new Error('Failed to fetch media settings')
      return response.json()
    },
    enabled: adminUser?.is_superuser,
  })

  useEffect(() => {
    if (settings?.max_folder_depth) {
      setLocalValue(settings.max_folder_depth)
    }
  }, [settings])

  const updateMutation = useMutation({
    mutationFn: async (newDepth: number) => {
      const response = await fetch('/api/admin/settings/media', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${useAuthStore.getState().token}`,
        },
        body: JSON.stringify({ max_folder_depth: newDepth }),
      })
      if (!response.ok) throw new Error('Failed to update media settings')
      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-media-settings'] })
      setShowSuccess(true)
      setTimeout(() => setShowSuccess(false), 3000)
    },
  })

  const handleSave = () => {
    updateMutation.mutate(localValue)
  }

  if (!adminUser?.is_superuser) return null

  return (
    <div className="border rounded-lg p-6">
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 bg-primary/10 rounded-lg">
          <Settings className="h-5 w-5 text-primary" />
        </div>
        <h2 className="text-lg font-semibold">Media Library Settings</h2>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Loading settings...</span>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="max-folder-depth">Maximum folder depth</Label>
            <div className="flex items-center gap-3">
              <Input
                id="max-folder-depth"
                type="number"
                min={1}
                value={localValue}
                onChange={(e) => setLocalValue(parseInt(e.target.value) || 1)}
                className="w-24"
              />
              <span className="text-sm text-muted-foreground">
                Maximum nesting level for media organization
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Button
              onClick={handleSave}
              disabled={updateMutation.isPending || (settings?.max_folder_depth === localValue)}
            >
              {updateMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save Changes'
              )}
            </Button>

            {showSuccess && (
              <span className="flex items-center gap-1 text-sm text-green-600">
                <CheckCircle className="h-4 w-4" />
                Settings updated
              </span>
            )}

            {updateMutation.isError && (
              <span className="flex items-center gap-1 text-sm text-destructive">
                <AlertCircle className="h-4 w-4" />
                Failed to save
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}