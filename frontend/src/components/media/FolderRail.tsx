import { useState, useRef, useEffect } from 'react'
import {
  ChevronRight,
  ChevronDown,
  Folder,
  MoreVertical,
  Plus,
  Pencil,
  Trash2,
  FolderPlus,
} from 'lucide-react'
import type { FolderTreeItem } from '../../api/types/media'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'
import { FolderCreateDialog } from './FolderCreateDialog'

interface FolderRailProps {
  folders: FolderTreeItem[]
  selectedId: string | undefined
  onSelect: (id: string | undefined) => void
  onCreateFolder: (name: string, parentId: string | null) => void
  onUpdateFolder: (id: string, payload: { name: string }) => void
  onDeleteFolder: (id: string) => void
  maxDepth?: number
}

interface FolderNodeProps {
  folder: FolderTreeItem
  level: number
  selectedId: string | undefined
  onSelect: (id: string | undefined) => void
  expandedIds: Set<string>
  onToggleExpand: (id: string) => void
  onRename: (id: string, name: string) => void
  onDelete: (id: string) => void
  onCreateSubfolder: (parentId: string) => void
  maxDepth: number
}

function FolderNode({
  folder,
  level,
  selectedId,
  onSelect,
  expandedIds,
  onToggleExpand,
  onRename,
  onDelete,
  onCreateSubfolder,
  maxDepth,
}: FolderNodeProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editName, setEditName] = useState(folder.name)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const hasChildren = folder.children && folder.children.length > 0
  const isSelected = selectedId === folder.id
  const isExpanded = expandedIds.has(folder.id)
  const isAtMaxDepth = level >= maxDepth - 1

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [isEditing])

  const handleDoubleClick = () => {
    setIsEditing(true)
    setEditName(folder.name)
  }

  const handleSaveRename = () => {
    if (editName.trim() && editName.trim() !== folder.name) {
      onRename(folder.id, editName.trim())
    } else {
      setEditName(folder.name)
    }
    setIsEditing(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSaveRename()
    } else if (e.key === 'Escape') {
      setEditName(folder.name)
      setIsEditing(false)
    }
  }

  const handleBlur = () => {
    handleSaveRename()
  }

  const handleCreateSubfolder = () => {
    setShowCreateDialog(true)
  }

  const handleCreateSubfolderConfirm = (_name: string, parentId: string | null) => {
    onCreateSubfolder(parentId!)
    setShowCreateDialog(false)
  }

  return (
    <div>
      <div
        className={`group flex items-center gap-1 px-2 py-1.5 rounded text-sm transition-colors ${
          isSelected
            ? 'bg-primary/10 text-primary'
            : 'hover:bg-muted text-muted-foreground'
        }`}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
      >
        {/* Expand/Collapse Chevron */}
        <button
          onClick={(e) => {
            e.stopPropagation()
            onToggleExpand(folder.id)
          }}
          className={`p-0.5 hover:bg-muted rounded ${
            !hasChildren ? 'invisible' : ''
          }`}
        >
          {isExpanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
        </button>

        {/* Folder Icon */}
        <Folder className="h-4 w-4 text-primary flex-shrink-0" />

        {/* Folder Name */}
        <button
          onClick={() => onSelect(folder.id)}
          onDoubleClick={handleDoubleClick}
          className="flex-1 text-left truncate"
        >
          {isEditing ? (
            <Input
              ref={inputRef}
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              onKeyDown={handleKeyDown}
              onBlur={handleBlur}
              className="h-6 px-1 py-0 text-sm"
            />
          ) : (
            <span className="truncate">{folder.name}</span>
          )}
        </button>

        {/* Context Menu Trigger */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              onClick={(e) => e.stopPropagation()}
              className="opacity-0 group-hover:opacity-100 p-1 hover:bg-muted rounded transition-opacity"
            >
              <MoreVertical className="h-3 w-3" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="right">
            <DropdownMenuItem onClick={handleDoubleClick}>
              <Pencil className="mr-2 h-4 w-4" />
              Rename
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={handleCreateSubfolder}
              disabled={isAtMaxDepth}
            >
              <FolderPlus className="mr-2 h-4 w-4" />
              New subfolder
              {isAtMaxDepth && (
                <span className="ml-auto text-xs text-muted-foreground">
                  (max depth)
                </span>
              )}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => onDelete(folder.id)}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Create Subfolder Dialog */}
      <FolderCreateDialog
        isOpen={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
        onCreate={handleCreateSubfolderConfirm}
        folders={[]}
        parentFolderId={folder.id}
        maxDepth={maxDepth}
        currentDepth={level}
      />

      {/* Children */}
      {isExpanded && hasChildren && (
        <div>
          {folder.children!.map((child) => (
            <FolderNode
              key={child.id}
              folder={child}
              level={level + 1}
              selectedId={selectedId}
              onSelect={onSelect}
              expandedIds={expandedIds}
              onToggleExpand={onToggleExpand}
              onRename={onRename}
              onDelete={onDelete}
              onCreateSubfolder={onCreateSubfolder}
              maxDepth={maxDepth}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function FolderRail({
  folders,
  selectedId,
  onSelect,
  onCreateFolder,
  onUpdateFolder,
  onDeleteFolder,
  maxDepth = 3,
}: FolderRailProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [showCreateDialog, setShowCreateDialog] = useState(false)

  const handleToggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleRename = (id: string, name: string) => {
    onUpdateFolder(id, { name })
  }

  const handleCreateSubfolder = () => {
    // This is called from context menu - we'll show the dialog inline
    // For now, just trigger the dialog at the parent level
    // The actual creation happens in the FolderNode component
  }

  const handleCreateRootFolder = (name: string, parentId: string | null) => {
    onCreateFolder(name, parentId)
    setShowCreateDialog(false)
  }

  // TODO: DnD drop target implementation for F8
  // This component will accept dropped assets and move them to the target folder
  // const [{ isOver }, drop] = useDrop(() => ({
  //   accept: [ASSET_ITEM_TYPE],
  //   drop: (item: AssetDragData) => {
  //     // Move asset to this folder
  //   },
  //   collect: (monitor) => ({
  //     isOver: monitor.isOver(),
  //   }),
  // }))

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto">
        <div className="space-y-0.5 p-2">
          {/* All Assets (Root) */}
          <button
            onClick={() => onSelect(undefined)}
            className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-colors ${
              selectedId === undefined
                ? 'bg-primary/10 text-primary'
                : 'hover:bg-muted text-muted-foreground'
            }`}
          >
            <Folder className="h-4 w-4 text-primary" />
            <span>All Assets</span>
          </button>

          {/* Folder Tree */}
          {folders.map((folder) => (
            <FolderNode
              key={folder.id}
              folder={folder}
              level={0}
              selectedId={selectedId}
              onSelect={onSelect}
              expandedIds={expandedIds}
              onToggleExpand={handleToggleExpand}
              onRename={handleRename}
              onDelete={onDeleteFolder}
              onCreateSubfolder={handleCreateSubfolder}
              maxDepth={maxDepth}
            />
          ))}
        </div>
      </div>

      {/* New Folder Button */}
      <div className="p-2 border-t">
        <Button
          variant="ghost"
          className="w-full justify-start gap-2"
          onClick={() => setShowCreateDialog(true)}
        >
          <Plus className="h-4 w-4" />
          New folder
        </Button>
      </div>

      {/* Create Folder Dialog */}
      <FolderCreateDialog
        isOpen={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
        onCreate={handleCreateRootFolder}
        folders={folders}
        maxDepth={maxDepth}
      />
    </div>
  )
}
