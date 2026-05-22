import { useQuery } from '@tanstack/react-query'
import { HardDrive, File } from 'lucide-react'
import { mediaKeys } from '../../hooks/useMedia'
import * as mediaApi from '../../api/media'
import type { StorageStats } from '../../api/types/media'

interface StorageStatsProps {
  className?: string
}

export function StorageStats({ className = '' }: StorageStatsProps) {
  const { data: stats, isLoading, error } = useQuery<StorageStats, Error>({
    queryKey: mediaKeys.stats(),
    queryFn: () => mediaApi.getStats(),
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }

  if (isLoading) {
    return (
      <div className={`flex items-center gap-4 text-sm text-muted-foreground ${className}`}>
        <div className="animate-pulse h-4 w-20 bg-muted rounded" />
        <div className="animate-pulse h-4 w-20 bg-muted rounded" />
      </div>
    )
  }

  if (error) {
    return null
  }

  return (
    <div className={`flex items-center gap-4 text-sm ${className}`}>
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <File className="w-4 h-4" />
        <span>{stats?.total_assets ?? 0} assets</span>
      </div>
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <HardDrive className="w-4 h-4" />
        <span>{formatFileSize(stats?.total_size_bytes ?? 0)}</span>
      </div>
    </div>
  )
}
