import { useState } from 'react'
import { ChevronRight, ChevronDown, Folder } from 'lucide-react'
import type { FolderTreeItem } from '../../api/types/media'

interface FolderTreeProps {
  folders: FolderTreeItem[]
  selectedId?: string
  onSelect: (folderId: string | undefined) => void
  level?: number
}

function FolderTreeNode({
  folder,
  selectedId,
  onSelect,
  level = 0,
}: {
  folder: FolderTreeItem
  selectedId?: string
  onSelect: (folderId: string | undefined) => void
  level?: number
}) {
  const [isExpanded, setIsExpanded] = useState(true)
  const hasChildren = folder.children && folder.children.length > 0
  const isSelected = selectedId === folder.id

  return (
    <div>
      <button
        onClick={() => onSelect(folder.id)}
        className={`w-full flex items-center gap-1 px-2 py-1.5 rounded text-sm transition-colors ${
          isSelected
            ? 'bg-primary/10 text-primary'
            : 'hover:bg-muted text-muted-foreground'
        }`}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
      >
        {hasChildren ? (
          <span
            onClick={(e) => {
              e.stopPropagation()
              setIsExpanded(!isExpanded)
            }}
            className="p-0.5 hover:bg-muted rounded"
          >
            {isExpanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </span>
        ) : (
          <span className="w-4" />
        )}
        <Folder className="h-4 w-4 text-primary" />
        <span className="truncate">{folder.name}</span>
      </button>

      {isExpanded && hasChildren && (
        <div>
          {folder.children!.map((child) => (
            <FolderTreeNode
              key={child.id}
              folder={child}
              selectedId={selectedId}
              onSelect={onSelect}
              level={level + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function FolderTree({ folders, selectedId, onSelect }: FolderTreeProps) {
  return (
    <div className="space-y-0.5">
      <button
        onClick={() => onSelect(undefined)}
        className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-colors ${
          !selectedId
            ? 'bg-primary/10 text-primary'
            : 'hover:bg-muted text-muted-foreground'
        }`}
      >
        <Folder className="h-4 w-4 text-primary" />
        <span>All Assets</span>
      </button>
      {folders.map((folder) => (
        <FolderTreeNode
          key={folder.id}
          folder={folder}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </div>
  )
}
