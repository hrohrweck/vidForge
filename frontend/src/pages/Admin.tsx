import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  RefreshCw,
  Users,
  Video,
  AlertCircle,
  CheckCircle,
  Clock,
  Loader2,
  Trash2,
  Shield,
  UserCog,
  ShieldOff,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { Button } from '../components/ui/button'
import { adminApi, UserDetail,
  DeletePreview,
  UserUpdateRequest,
  Job,
} from '../api/client'
import { DeleteConfirmationModal } from '../components/DeleteConfirmationModal'

interface AdminUser extends UserDetail {
  groups: { id: string; name: string }[]
}

export default function Admin() {
  const navigate = useNavigate()
  const { user: adminUser } = useAuthStore()
  const queryClient = useQueryClient()

  const [deleteModal, setDeleteModal] = useState<{
    isOpen: boolean
    userId: string | null
    preview: DeletePreview | null
  }>({ isOpen: false, userId: null, preview: null })

  const { data: dashboard, isLoading, refetch } = useQuery({
    queryKey: ['admin-dashboard'],
    queryFn: async () => {
      const response = await fetch('/api/admin/dashboard', {
        headers: {
          Authorization: `Bearer ${useAuthStore.getState().token}`,
        },
      })
      if (!response.ok) throw new Error('Failed to fetch dashboard')
      return response.json()
    },
    enabled: adminUser?.is_superuser,
  })

  const { data: users, refetch: refetchUsers } = useQuery({
    queryKey: ['admin-users'],
    queryFn: async () => {
      const response = await fetch('/api/admin/users', {
        headers: {
          Authorization: `Bearer ${useAuthStore.getState().token}`,
        },
      })
      if (!response.ok) throw new Error('Failed to fetch users')
      return response.json()
    },
    enabled: adminUser?.is_superuser,
  })

  const retryMutation = useMutation({
    mutationFn: (jobId: string) =>
      fetch(`/api/admin/jobs/${jobId}/retry`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${useAuthStore.getState().token}`,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) =>
      fetch(`/api/admin/jobs/${jobId}/cancel`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${useAuthStore.getState().token}`,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] })
    },
  })

  const updateUserMutation = useMutation({
    mutationFn: async ({ userId, data }: { userId: string; data: UserUpdateRequest }) => {
      return adminApi.updateUser(userId, data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      refetchUsers()
    },
  })

  const deleteUserMutation = useMutation({
    mutationFn: async (userId: string) => {
      return adminApi.deleteUser(userId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] })
      setDeleteModal({ isOpen: false, userId: null, preview: null })
    },
  })

  const previewDeleteMutation = useMutation({
    mutationFn: async (userId: string) => {
      return adminApi.previewUserDeletion(userId)
    },
    onSuccess: (data, userId) => {
      setDeleteModal({ isOpen: true, userId, preview: data })
    },
  })

  if (!adminUser?.is_superuser) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <AlertCircle className="h-8 w-8 text-red-500 mb-4" />
        <h2 className="text-xl font-semibold">Access Denied</h2>
        <p className="text-muted-foreground">You need admin privileges to view this page</p>
        <Button className="mt-4" onClick={() => navigate('/')}>
          Go to Dashboard
        </Button>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const stats = dashboard?.stats
  const recentJobs = dashboard?.recent_jobs || []

  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    processing: 'bg-blue-100 text-blue-800',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
    cancelled: 'bg-gray-100 text-gray-800',
  }

  const handleToggleAdmin = async (targetUser: AdminUser) => {
    if (targetUser.id === adminUser?.id) {
      alert('Cannot modify your own admin status')
      return
    }
    await updateUserMutation.mutate({
      userId: targetUser.id,
      data: { is_superuser: !targetUser.is_superuser },
    })
  }

  const handleToggleActive = async (targetUser: AdminUser) => {
    if (targetUser.id === adminUser?.id) {
      alert('Cannot deactivate yourself')
      return
    }
    await updateUserMutation.mutate({
      userId: targetUser.id,
      data: { is_active: !targetUser.is_active },
    })
  }

  const handleDeleteClick = async (targetUser: AdminUser) => {
    if (targetUser.id === adminUser?.id) {
      alert('Cannot delete yourself')
      return
    }
    await previewDeleteMutation.mutate(targetUser.id)
  }

  const handleConfirmDelete = async () => {
    if (deleteModal.userId)
    {
      await deleteUserMutation.mutate(deleteModal.userId)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Admin Dashboard</h1>
          <p className="text-muted-foreground">System overview and user management</p>
        </div>
        <Button variant="outline" onClick={() => refetch()}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="border rounded-lg p-6">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-blue-100 rounded-lg">
              <Users className="h-6 w-6 text-blue-600" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Total Users</p>
              <p className="text-2xl font-bold">{stats?.total_users || 0}</p>
            </div>
          </div>
        </div>

        <div className="border rounded-lg p-6">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-purple-100 rounded-lg">
              <Video className="h-6 w-6 text-purple-600" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Total Jobs</p>
              <p className="text-2xl font-bold">{stats?.total_jobs || 1}</p>
            </div>
          </div>
        </div>

        <div className="border rounded-lg p-6">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-green-100 rounded-lg">
              <CheckCircle className="h-6 w-6 text-green-600" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Jobs Today</p>
              <p className="text-2xl font-bold">{stats?.jobs_today || 1}</p>
            </div>
          </div>
        </div>

        <div className="border rounded-lg p-6">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-orange-100 rounded-lg">
              <Clock className="h-6 w-6 text-orange-600" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">This Week</p>
              <p className="text-2xl font-bold">{stats?.jobs_this_week || 1}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="border rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Users</h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-3 px-4">Email</th>
                <th className="text-left py-3 px-4">Status</th>
                <th className="text-left py-3 px-4">Groups</th>
                <th className="text-left py-3 px-4">Jobs</th>
                <th className="text-left py-3 px-4">Joined</th>
                <th className="text-left py-3 px-4">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users?.map((u: AdminUser) => (
                <tr key={u.id} className="border-b hover:bg-gray-50">
                  <td className="py-3 px-4">{u.email}</td>
                  <td className="py-3 px-4">
                    <div className="flex gap-1">
                      {u.is_superuser && (
                        <span className="px-2 py-1 rounded-full text-xs bg-purple-100 text-purple-800">
                          Admin
                        </span>
                      )}
                      {u.is_active ? (
                        <span className="px-2 py-1 rounded-full text-xs bg-green-100 text-green-800">
                          Active
                        </span>
                      ) : (
                        <span className="px-2 py-1 rounded-full text-xs bg-red-100 text-red-800">
                          Inactive
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex gap-1 flex-wrap">
                      {u.groups?.map((g) => (
                        <span
                          key={g.id}
                          className="px-2 py-1 rounded-full text-xs bg-gray-100 text-gray-800"
                        >
                          {g.name}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="py-3 px-4">{u.jobs_count}</td>
                  <td className="py-3 px-4 text-sm text-muted-foreground">
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleToggleAdmin(u)}
                        disabled={u.id === adminUser?.id}
                        title={u.is_superuser ? 'Remove Admin' : 'Make Admin'}
                      >
                        {u.is_superuser ? (
                          <ShieldOff className="h-4 w-4" />
                        ) : (
                          <Shield className="h-4 w-4" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleToggleActive(u)}
                        disabled={u.id === adminUser?.id}
                        title={u.is_active ? 'Deactivate' : 'Activate'}
                      >
                        {u.is_active ? (
                          <UserCog className="h-4 w-4" />
                        ) : (
                          <UserCog className="h-4 w-4" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteClick(u)}
                        disabled={u.id === adminUser?.id}
                        title="Delete User"
                      >
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="border rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">Recent Jobs</h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-3 px-4">ID</th>
                <th className="text-left py-3 px-4">User</th>
                <th className="text-left py-3 px-4">Status</th>
                <th className="text-left py-3 px-4">Progress</th>
                <th className="text-left py-3 px-4">Created</th>
                <th className="text-left py-3 px-4">Actions</th>
              </tr>
            </thead>
            <tbody>
              {recentJobs.map((job: Job & { user_email?: string }) => (
                <tr key={job.id} className="border-b hover:bg-gray-50">
                  <td className="py-3 px-4 font-mono text-sm">
                    {job.id.slice(0, 8)}...
                  </td>
                  <td className="py-3 px-4">{job.user_email || 'Unknown'}</td>
                  <td className="py-3 px-4">
                    <span
                      className={`px-2 py-1 rounded-full text-xs font-medium ${statusColors[job.status]}`}
                    >
                      {job.status}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <div className="w-20 bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-blue-600 h-2 rounded-full"
                          style={{ width: `${job.progress}%` }}
                        />
                      </div>
                      <span className="text-sm text-muted-foreground">{job.progress}%</span>
                    </div>
                  </td>
                  <td className="py-3 px-4 text-sm text-muted-foreground">
                    {new Date(job.created_at).toLocaleString()}
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex gap-2">
                      {job.status === 'failed' && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => retryMutation.mutate(job.id)}
                        >
                          Retry
                        </Button>
                      )}
                      {(job.status === 'pending' || job.status === 'processing') && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => cancelMutation.mutate(job.id)}
                        >
                          Cancel
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => navigate(`/jobs/${job.id}`)}
                      >
                        View
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <DeleteConfirmationModal
        isOpen={deleteModal.isOpen}
        onClose={() => setDeleteModal({ isOpen: false, userId: null, preview: null })}
        onConfirm={handleConfirmDelete}
        title="Delete User"
        message={`You are about to delete user: ${deleteModal.preview?.email}`}
        itemsToDelete={deleteModal.preview?.items_to_delete || {}}
        warning={deleteModal.preview?.warning}
        isLoading={deleteUserMutation.isPending}
      />
    </div>
  )
}
