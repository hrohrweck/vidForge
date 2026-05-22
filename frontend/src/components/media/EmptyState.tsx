import { FolderOpen, Search, Image } from 'lucide-react'

interface EmptyStateProps {
  type?: 'no-folder' | 'no-results' | 'no-assets'
  searchQuery?: string
  onUpload?: () => void
}

export function EmptyState({
  type = 'no-assets',
  searchQuery,
  onUpload,
}: EmptyStateProps) {
  const renderContent = () => {
    switch (type) {
      case 'no-folder':
        return {
          icon: <FolderOpen className="w-16 h-16 text-muted-foreground/50" />,
          title: 'No folder selected',
          description: 'Select a folder from the sidebar to view its contents',
        }

      case 'no-results':
        return {
          icon: <Search className="w-16 h-16 text-muted-foreground/50" />,
          title: 'No results found',
          description: searchQuery
            ? `No assets match "${searchQuery}"`
            : 'Try adjusting your filters',
        }

      case 'no-assets':
      default:
        return {
          icon: <Image className="w-16 h-16 text-muted-foreground/50" />,
          title: 'This folder is empty',
          description: 'Upload some media files to get started',
        }
    }
  }

  const { icon, title, description } = renderContent()

  return (
    <div className="flex flex-col items-center justify-center h-full text-center p-8">
      {icon}
      <h3 className="mt-6 text-lg font-medium">{title}</h3>
      <p className="mt-2 text-sm text-muted-foreground max-w-md">
        {description}
      </p>
      {onUpload && type === 'no-assets' && (
        <button
          onClick={onUpload}
          className="mt-6 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
        >
          Upload Files
        </button>
      )}
    </div>
  )
}
