import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Edit2, Trash2, Shield, Loader2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { Button } from '../components/ui/button'
import { adminApi, Group, Permission } from '../api/client'
import { DeleteConfirmationModal } from '../components/DeleteConfirmationModal'

interface GroupWithPermissions extends Group {
  permissions: Permission[]
}

export default function Groups() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const queryClient = useQueryClient()

  const [deleteModal, setDeleteModal] = useState<{
    isOpen: boolean
    groupId: string | null
    groupName: string | null
  }>({ isOpen: false, groupId: null, groupName: null })

  const [editModal, setEditModal] = useState<{
    isOpen: boolean
    group: GroupWithPermissions | null
  }>({ isOpen: false, group: null })

  const [createModal, setCreateModal] = useState(false)

  const { data: groups, isLoading } = useQuery({
    queryKey: ['admin-groups'],
    queryFn: async () => {
      return adminApi.getGroups()
    },
    enabled: user?.is_superuser,
  })

  const { data: permissions } = useQuery({
    queryKey: ['admin-permissions'],
    queryFn: async () => {
      return adminApi.getPermissions()
    },
    enabled: user?.is_superuser,
  })

  const deleteGroupMutation = useMutation({
    mutationFn: async (groupId: string) => {
      return adminApi.deleteGroup(groupId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-groups'] })
      setDeleteModal({ isOpen: false, groupId: null, groupName: null })
    },
  })

  const handleDeleteClick = (group: GroupWithPermissions) => {
    if (group.name === 'users' || group.name === 'admins') {
      alert('Cannot delete system groups')
      return
    }
    setDeleteModal({ isOpen: true, groupId: group.id, groupName: group.name })
  }

  if (!user?.is_superuser) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <Shield className="h-8 w-8 text-red-500 mb-4" />
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

  const groupedPermissions = (permissions || []).reduce((acc, perm) => {
    if (!acc[perm.category]) acc[perm.category] = []
    acc[perm.category].push(perm)
    return acc
  }, {} as Record<string, Permission[]>)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Groups & Permissions</h1>
          <p className="text-muted-foreground">Manage user groups and their permissions</p>
        </div>
        <Button onClick={() => setCreateModal(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Create Group
        </Button>
      </div>

      <div className="grid gap-4">
        {groups?.map((group) => (
          <div key={group.id} className="border rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold">{group.name}</h3>
                {group.description && (
                  <p className="text-sm text-muted-foreground">{group.description}</p>
                )}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setEditModal({ isOpen: true, group: group as GroupWithPermissions })}
                >
                  <Edit2 className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDeleteClick(group as GroupWithPermissions)}
                  disabled={group.name === 'users' || group.name === 'admins'}
                >
                  <Trash2 className="h-4 w-4 text-red-500" />
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              {Object.entries(groupedPermissions).map(([category, perms]) => (
                <div key={category}>
                  <p className="text-sm font-medium capitalize mb-1">{category}</p>
                  <div className="flex flex-wrap gap-2">
                    {perms.map((perm) => {
                      const hasPermission = group.permissions?.some((p) => p.id === perm.id)
                      return (
                        <span
                          key={perm.id}
                          className={`px-2 py-1 rounded text-xs ${
                            hasPermission
                              ? 'bg-green-100 text-green-800'
                              : 'bg-gray-100 text-gray-400'
                          }`}
                        >
                          {perm.name}
                        </span>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <DeleteConfirmationModal
        isOpen={deleteModal.isOpen}
        onClose={() => setDeleteModal({ isOpen: false, groupId: null, groupName: null })}
        onConfirm={() => deleteModal.groupId && deleteGroupMutation.mutate(deleteModal.groupId)}
        title="Delete Group"
        message={`Are you sure you want to delete the group "${deleteModal.groupName}"?`}
        itemsToDelete={{}}
        warning="Users in this group will lose their group assignment."
        isLoading={deleteGroupMutation.isPending}
      />

      {createModal && (
        <GroupEditModal
          isOpen={createModal}
          onClose={() => setCreateModal(false)}
          groupedPermissions={groupedPermissions}
        />
      )}

      {editModal.isOpen && editModal.group && (
        <GroupEditModal
          isOpen={editModal.isOpen}
          onClose={() => setEditModal({ isOpen: false, group: null })}
          group={editModal.group}
          groupedPermissions={groupedPermissions}
        />
      )}
    </div>
  )
}

function GroupEditModal({
  isOpen,
  onClose,
  group,
  groupedPermissions,
}: {
  isOpen: boolean
  onClose: () => void
  group?: GroupWithPermissions | null
  groupedPermissions: Record<string, Permission[]>
}) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(group?.name || '')
  const [description, setDescription] = useState(group?.description || '')
  const [selectedPermissions, setSelectedPermissions] = useState<Set<string>>(
    new Set(group?.permissions?.map((p) => p.id) || [])
  )

  const saveMutation = useMutation({
    mutationFn: async () => {
      const data = {
        name,
        description,
        permission_ids: Array.from(selectedPermissions),
      }
      if (group) {
        return adminApi.updateGroup(group.id, data)
      } else {
        return adminApi.createGroup(data)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-groups'] })
      onClose()
    },
  })

  const togglePermission = (permId: string) => {
    const newSet = new Set(selectedPermissions)
    if (newSet.has(permId)) {
      newSet.delete(permId)
    } else {
      newSet.add(permId)
    }
    setSelectedPermissions(newSet)
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background rounded-lg p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
        <h2 className="text-xl font-semibold mb-4">
          {group ? 'Edit Group' : 'Create Group'}
        </h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full border rounded px-3 py-2"
              placeholder="Group name"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full border rounded px-3 py-2"
              placeholder="Group description"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Permissions</label>
            <div className="space-y-3">
              {Object.entries(groupedPermissions).map(([category, perms]) => (
                <div key={category}>
                  <p className="text-sm font-medium capitalize mb-1">{category}</p>
                  <div className="flex flex-wrap gap-2">
                    {perms.map((perm) => (
                      <button
                        key={perm.id}
                        onClick={() => togglePermission(perm.id)}
                        className={`px-2 py-1 rounded text-xs border ${
                          selectedPermissions.has(perm.id)
                            ? 'bg-green-100 text-green-800 border-green-300'
                            : 'bg-gray-100 text-gray-600 border-gray-300'
                        }`}
                      >
                        {perm.name}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => saveMutation.mutate()} disabled={!name || saveMutation.isPending}>
            {saveMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : null}
            {group ? 'Save Changes' : 'Create Group'}
          </Button>
        </div>
      </div>
    </div>
  )
}
