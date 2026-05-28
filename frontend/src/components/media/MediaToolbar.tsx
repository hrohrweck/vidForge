import { useState, useEffect, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { AssetListQuery, FileType } from '../../api/types/media'
import QuickCreateMedia from '../QuickCreateMedia'
import { Input } from '../ui/input'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select'
import { Grid3x3, List, LayoutGrid, Upload, Search, X } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface MediaToolbarProps {
  query: AssetListQuery
  onQueryChange: (query: AssetListQuery) => void
  view: string
  onViewChange: (view: string) => void
  onUploadClick: () => void
  breadcrumbs?: { id: string | null; name: string }[]
  stats?: {
    itemCount: number
    totalSize: number
  }
}

const FILE_TYPE_FILTERS: { value: FileType | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'image', label: 'Images' },
  { value: 'video', label: 'Videos' },
  { value: 'audio', label: 'Audio' },
  { value: 'markdown', label: 'Docs' },
]

const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: 'created_at-desc', label: 'Recent' },
  { value: 'name-asc', label: 'Name A→Z' },
  { value: 'name-desc', label: 'Name Z→A' },
  { value: 'size_bytes-desc', label: 'Largest' },
  { value: 'size_bytes-asc', label: 'Smallest' },
]

const VIEW_STORAGE_KEY = 'vidforge_media_view'

export function MediaToolbar({
  query,
  onQueryChange,
  view,
  onViewChange,
  onUploadClick,
  breadcrumbs = [],
  stats,
}: MediaToolbarProps) {
  const queryClient = useQueryClient()
  const [searchValue, setSearchValue] = useState(query.search || '')

  // Debounced search - 300ms delay
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchValue) {
        onQueryChange({ ...query, search: searchValue })
      } else {
        // Clear search when empty
        const { search, ...rest } = query
        onQueryChange(rest as AssetListQuery)
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [searchValue])

  // Clear search when folder changes
  useEffect(() => {
    setSearchValue(query.search || '')
  }, [query.folder_id])

  // Load view preference from localStorage on mount
  useEffect(() => {
    const savedView = localStorage.getItem(VIEW_STORAGE_KEY)
    if (savedView && savedView !== view) {
      onViewChange(savedView)
    }
  }, [])

  // Persist view changes to localStorage
  const handleViewChange = useCallback(
    (newView: string) => {
      localStorage.setItem(VIEW_STORAGE_KEY, newView)
      onViewChange(newView)
    },
    [onViewChange]
  )

  const handleSortChange = (value: string) => {
    const [sort_by, sort_order] = value.split('-') as [
      'created_at' | 'name' | 'size_bytes',
      'asc' | 'desc',
    ]
    onQueryChange({ ...query, sort_by, sort_order })
  }

  const handleTypeFilterChange = (fileType: FileType | 'all') => {
    if (fileType === 'all') {
      onQueryChange({ ...query, file_type: undefined })
    } else {
      onQueryChange({ ...query, file_type: fileType })
    }
  }

  const handleClearSearch = () => {
    setSearchValue('')
  }

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
  }

  const currentSort = query.sort_by && query.sort_order
    ? `${query.sort_by}-${query.sort_order}`
    : 'created_at-desc'

  return (
    <div className="border-b border-border bg-background sticky top-0 z-10">
      <div className="p-4 space-y-3">
        {/* Top Row: Breadcrumb, Search, Sort, View Toggle, Upload */}
        <div className="flex items-center justify-between gap-4">
          {/* Left: Breadcrumb + Search */}
          <div className="flex items-center gap-4 flex-1 min-w-0">
            {/* Breadcrumb */}
            {breadcrumbs.length > 0 && (
              <nav className="flex items-center gap-2 text-sm text-muted-foreground flex-shrink-0">
                {breadcrumbs.map((crumb, index) => (
                  <div key={crumb.id || 'root'} className="flex items-center gap-2">
                    {index > 0 && <span className="text-muted-foreground">/</span>}
                    <span
                      className={cn(
                        'hover:text-foreground cursor-pointer transition-colors',
                        index === breadcrumbs.length - 1 &&
                          'font-medium text-foreground'
                      )}
                    >
                      {crumb.name}
                    </span>
                  </div>
                ))}
              </nav>
            )}

            {/* Search Input */}
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Search assets..."
                value={searchValue}
                onChange={(e) => setSearchValue(e.target.value)}
                className="pl-9 pr-8"
              />
              {searchValue && (
                <button
                  onClick={handleClearSearch}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-muted rounded-full transition-colors"
                  type="button"
                >
                  <X className="h-3 w-3 text-muted-foreground" />
                </button>
              )}
            </div>
          </div>

          {/* Right: Sort + View Toggle + Upload */}
          <div className="flex items-center gap-2">
            {/* Sort Dropdown */}
            <Select value={currentSort} onValueChange={handleSortChange}>
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="Sort by" />
              </SelectTrigger>
              <SelectContent>
                {SORT_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* View Toggle */}
            <div className="flex items-center gap-1 border border-input rounded-md p-1">
              <button
                onClick={() => handleViewChange('grid')}
                className={cn(
                  'p-1.5 rounded transition-colors',
                  view === 'grid'
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted text-muted-foreground'
                )}
                title="Grid View"
                type="button"
              >
                <Grid3x3 className="h-4 w-4" />
              </button>
              <button
                onClick={() => handleViewChange('list')}
                className={cn(
                  'p-1.5 rounded transition-colors',
                  view === 'list'
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted text-muted-foreground'
                )}
                title="List View"
                type="button"
              >
                <List className="h-4 w-4" />
              </button>
              <button
                onClick={() => handleViewChange('masonry')}
                className={cn(
                  'p-1.5 rounded transition-colors',
                  view === 'masonry'
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted text-muted-foreground'
                )}
                title="Masonry View"
                type="button"
              >
                <LayoutGrid className="h-4 w-4" />
              </button>
            </div>

            {/* Upload Button */}
            <Button onClick={onUploadClick} size="sm">
              <Upload className="h-4 w-4 mr-2" />
              Upload
            </Button>

            {/* Quick Create Media */}
            <QuickCreateMedia
              onSuccess={() => queryClient.invalidateQueries({ queryKey: ['media'] })}
            />
          </div>
        </div>

        {/* Bottom Row: Type Filter Chips + Stats */}
        <div className="flex items-center justify-between">
          {/* Type Filter Chips */}
          <div className="flex items-center gap-2">
            {FILE_TYPE_FILTERS.map((filter) => {
              const isActive =
                (filter.value === 'all' && !query.file_type) ||
                query.file_type === filter.value

              return (
                <Badge
                  key={filter.value}
                  variant={isActive ? 'default' : 'outline'}
                  className={cn(
                    'cursor-pointer transition-colors',
                    !isActive && 'hover:bg-muted'
                  )}
                  onClick={() => handleTypeFilterChange(filter.value)}
                >
                  {filter.label}
                </Badge>
              )
            })}
          </div>

          {/* Storage Stats */}
          {stats && (
            <div className="text-sm text-muted-foreground">
              {stats.itemCount} items · {formatBytes(stats.totalSize)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
