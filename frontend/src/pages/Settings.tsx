import { useQuery } from '@tanstack/react-query'
import { storageApi, stylesApi } from '../api/client'
import { useAuthStore } from '../stores/auth'

export default function Settings() {
  const { user } = useAuthStore()

  const { data: storageConfig } = useQuery({
    queryKey: ['storage-config'],
    queryFn: () => storageApi.getConfig(),
  })

  const { data: styles } = useQuery({
    queryKey: ['styles'],
    queryFn: () => stylesApi.list(),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-muted-foreground">Manage your account and preferences</p>
      </div>

      <div className="space-y-6">
        <div className="border rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Account</h2>
          <div className="space-y-2">
            <p className="text-sm">
              <span className="text-muted-foreground">Email:</span> {user?.email}
            </p>
            <p className="text-sm">
              <span className="text-muted-foreground">Status:</span>{' '}
              {user?.is_active ? 'Active' : 'Inactive'}
            </p>
          </div>
        </div>

        <div className="border rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Storage</h2>
          <div className="space-y-2">
            <p className="text-sm">
              <span className="text-muted-foreground">Backend:</span>{' '}
              {storageConfig?.data.backend}
            </p>
          </div>
        </div>

        <div className="border rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Available Styles</h2>
          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
            {styles?.map((style) => (
              <div key={style.id} className="p-3 bg-secondary rounded-md">
                <p className="font-medium">{style.name}</p>
                {style.category && (
                  <p className="text-xs text-muted-foreground">{style.category}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
