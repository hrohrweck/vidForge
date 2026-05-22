import { useState, useCallback } from 'react'
import api from '../api/client'

interface UseBulkDownloadReturn {
  /** Whether a download is currently in progress */
  isDownloading: boolean
  /** Error message if download failed */
  error: string | null
  /** Initiate download of selected assets as ZIP */
  download: (assetIds: string[]) => Promise<void>
  /** Clear any error state */
  clearError: () => void
}

/**
 * Hook for handling bulk download of media assets as ZIP.
 * Manages download state, error handling, and blob cleanup.
 */
export function useBulkDownload(): UseBulkDownloadReturn {
  const [isDownloading, setIsDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const clearError = useCallback(() => {
    setError(null)
  }, [])

  const download = useCallback(async (assetIds: string[]) => {
    if (assetIds.length === 0) {
      setError('No assets selected for download')
      return
    }

    setIsDownloading(true)
    setError(null)

    try {
      // POST to bulk download endpoint
      const response = await api.post('/media/assets/bulk/download', {
        asset_ids: assetIds,
      }, {
        responseType: 'blob',
      })

      // Create blob from response
      const blob = new Blob([response.data], { type: 'application/zip' })
      
      // Create object URL and trigger download
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      
      // Generate filename with timestamp
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5)
      link.download = `vidforge-download-${timestamp}.zip`
      
      // Trigger download
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      
      // Cleanup object URL after delay
      setTimeout(() => {
        URL.revokeObjectURL(url)
      }, 1000)
    } catch (err) {
      console.error('Bulk download failed:', err)
      setError(err instanceof Error ? err.message : 'Download failed. Please try again.')
    } finally {
      setIsDownloading(false)
    }
  }, [])

  return {
    isDownloading,
    error,
    download,
    clearError,
  }
}
