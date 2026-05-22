import { useState, useEffect } from 'react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog'
import { Label } from '../ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select'
import type { FolderTreeItem } from '../../api/types/media'

interface FolderCreateDialogProps {
  isOpen: boolean
  onClose: () => void
  onCreate: (name: string, parentId: string | null) => void
  folders: FolderTreeItem[]
  parentFolderId?: string | null
  maxDepth?: number
  currentDepth?: number
}

export function FolderCreateDialog({
  isOpen,
  onClose,
  onCreate,
  folders,
  parentFolderId,
  maxDepth = 3,
  currentDepth = 0,
}: FolderCreateDialogProps) {
  const [folderName, setFolderName] = useState('')
  const [selectedParentId, setSelectedParentId] = useState<string>(
    parentFolderId ?? ''
  )
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Reset form when dialog opens
  useEffect(() => {
    if (isOpen) {
      setFolderName('')
      setSelectedParentId(parentFolderId ?? '')
      setIsSubmitting(false)
    }
  }, [isOpen, parentFolderId])

  // Build flat list of folders with their depth for the dropdown
  const buildFolderOptions = (
    folderList: FolderTreeItem[],
    depth = 0,
    result: Array<{ id: string; name: string; depth: number }> = []
  ): Array<{ id: string; name: string; depth: number }> => {
    for (const folder of folderList) {
      result.push({
        id: folder.id,
        name: folder.name,
        depth,
      })
      if (folder.children && depth + 1 < maxDepth) {
        buildFolderOptions(folder.children, depth + 1, result)
      }
    }
    return result
  }

  const folderOptions = buildFolderOptions(folders)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!folderName.trim() || isSubmitting) return

    // Check if we're at max depth
    const selectedDepth =
      selectedParentId === ''
        ? 0
        : folderOptions.find((f) => f.id === selectedParentId)?.depth ?? 0

    if (selectedDepth + 1 >= maxDepth) {
      // Silently prevent creation at max depth
      return
    }

    setIsSubmitting(true)
    try {
      await onCreate(folderName.trim(), selectedParentId === '' ? null : selectedParentId)
      onClose()
    } catch (error) {
      console.error('Failed to create folder:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const isAtMaxDepth =
    selectedParentId === ''
      ? currentDepth >= maxDepth - 1
      : (folderOptions.find((f) => f.id === selectedParentId)?.depth ?? 0) >=
        maxDepth - 1

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Create New Folder</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="folder-name">Folder Name</Label>
              <Input
                id="folder-name"
                value={folderName}
                onChange={(e) => setFolderName(e.target.value)}
                placeholder="Enter folder name"
                autoFocus
                disabled={isSubmitting}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="parent-folder">Parent Folder</Label>
              <Select
                value={selectedParentId}
                onValueChange={setSelectedParentId}
                disabled={isSubmitting}
              >
                <SelectTrigger id="parent-folder">
                  <SelectValue placeholder="Select parent folder" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">Root (All Assets)</SelectItem>
                  {folderOptions.map((folder) => (
                    <SelectItem key={folder.id} value={folder.id}>
                      {'\u00A0\u00A0'.repeat(folder.depth)}📁 {folder.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {isAtMaxDepth && (
                <p className="text-xs text-muted-foreground">
                  Maximum folder depth ({maxDepth}) reached
                </p>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!folderName.trim() || isAtMaxDepth || isSubmitting}
            >
              {isSubmitting ? 'Creating...' : 'Create Folder'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
