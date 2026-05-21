import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listProjects } from '../api/projects'
import type { Project } from '../api/types/project'
import { MediaGrid } from '../components/media/MediaGrid'
import { FolderTree } from '../components/media/FolderTree'
import { MediaUploader } from '../components/media/MediaUploader'
import { useFolderTree } from '../hooks/useMedia'
import type { MediaAsset, AssetListQuery } from '../api/types/media'

export function MediaLibrary() {
  const navigate = useNavigate()
  const [selectedFolder, setSelectedFolder] = useState<string | undefined>()
  const [selectedProject, setSelectedProject] = useState<string | undefined>()
  const [selectedAssets, setSelectedAssets] = useState<Set<string>>(new Set())
  const [isSelectMode, setIsSelectMode] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [showUploader, setShowUploader] = useState(false)

  const { data: folderTree } = useFolderTree()
  const { data: projects } = useQuery({
    queryKey: ['projects'],
    queryFn: () => listProjects(),
  })

  const query: AssetListQuery = {
    folder_id: selectedFolder,
    project_id: selectedProject,
    search: searchQuery || undefined,
    limit: 50,
  }

  const handleAssetClick = (asset: MediaAsset) => {
    navigate(`/media/asset/${asset.id}`)
  }

  const handleSelectAsset = (asset: MediaAsset, selected: boolean) => {
    setSelectedAssets((prev) => {
      const next = new Set(prev)
      if (selected) {
        next.add(asset.id)
      } else {
        next.delete(asset.id)
      }
      return next
    })
  }

  return (
    <div className="flex h-screen">
      {/* Sidebar - Folder Tree */}
      <div className="w-64 border-r border-border p-4 overflow-y-auto">
        <h2 className="text-lg font-semibold mb-4">Folders</h2>
        {folderTree && (
          <FolderTree
            folders={folderTree}
            selectedId={selectedFolder}
            onSelect={setSelectedFolder}
          />
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="border-b border-border p-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <input
              type="text"
              placeholder="Search assets..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="px-3 py-2 border border-input rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <select
              value={selectedProject || ''}
              onChange={(e) => setSelectedProject(e.target.value || undefined)}
              className="px-3 py-2 border border-input rounded-md"
            >
              <option value="">All Projects</option>
              {projects?.map((project: Project) => (
                <option key={project.id} value={project.id}>
                  {project.title}
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                setIsSelectMode(!isSelectMode)
                setSelectedAssets(new Set())
              }}
              className={`px-3 py-2 rounded-md ${
                isSelectMode
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted hover:bg-muted/80'
              }`}
            >
              {isSelectMode ? 'Done' : 'Select'}
            </button>
            <button
              onClick={() => setShowUploader(!showUploader)}
              className="px-3 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
            >
              {showUploader ? 'Hide Upload' : 'Upload'}
            </button>
          </div>

          {isSelectMode && selectedAssets.size > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">
                {selectedAssets.size} selected
              </span>
              <button className="px-3 py-2 bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90">
                Delete
              </button>
            </div>
          )}
        </div>

        {/* Upload Area */}
        {showUploader && (
          <div className="border-b border-border p-4 bg-muted/50">
            <MediaUploader
              folderId={selectedFolder}
              onUploadComplete={() => setShowUploader(false)}
            />
          </div>
        )}

        {/* Asset Grid */}
        <div className="flex-1 overflow-y-auto p-4">
          <MediaGrid
            query={query}
            selectable={isSelectMode}
            selectedAssets={selectedAssets}
            onSelectAsset={handleSelectAsset}
            onAssetClick={handleAssetClick}
          />
        </div>
      </div>
    </div>
  )
}
