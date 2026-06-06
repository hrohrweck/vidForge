import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/utils'
import { MediaCanvas } from '../MediaCanvas'
import type { MediaAsset } from '../../../api/types/media'

// Mock IntersectionObserver for infinite scroll
class MockIntersectionObserver implements IntersectionObserver {
  root: Document | Element | null = null
  rootMargin: string = ''
  thresholds: ReadonlyArray<number> = []
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
  takeRecords = vi.fn(() => [])
}

Object.defineProperty(window, 'IntersectionObserver', {
  writable: true,
  configurable: true,
  value: MockIntersectionObserver,
})

const createMockAsset = (overrides?: Partial<MediaAsset>): MediaAsset => ({
  id: 'test-asset-1',
  user_id: 'user-1',
  folder_id: null,
  name: 'Test Asset',
  file_path: '/path/to/asset.mp4',
  file_type: 'video',
  mime_type: 'video/mp4',
  size_bytes: 1024000,
  preview_path: '/path/to/preview.jpg',
  source_type: 'generated',
  source_job_id: 'job-1',
  asset_metadata: { width: 1920, height: 1080 },
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  tags: [],
  ...overrides,
})

const createMockSelection = (selectedIds: string[] = []) => ({
  isSelected: vi.fn((id: string) => selectedIds.includes(id)),
  count: selectedIds.length,
  toggle: vi.fn(),
  selectOnly: vi.fn(),
  selectAll: vi.fn(),
  clear: vi.fn(),
  range: vi.fn(),
  selectedIds: new Set(selectedIds),
  anchorId: null as string | null,
})

describe('MediaCanvas', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('list view thumbnail rendering', () => {
    it('renders image with preview_path using preview URL', () => {
      const asset = createMockAsset({
        id: 'img-preview',
        name: 'Image With Preview.jpg',
        file_type: 'image',
        preview_path: '/path/to/preview.jpg',
      })
      const selection = createMockSelection()
      renderWithProviders(
        <MediaCanvas
          assets={[asset]}
          view="list"
          selection={selection}
        />
      )
      const img = screen.getByRole('img', { name: 'Image With Preview.jpg' })
      expect(img).toHaveAttribute('src', '/api/media/assets/img-preview/preview')
    })

    it('renders image without preview_path using file URL', () => {
      const asset = createMockAsset({
        id: 'img-no-preview',
        name: 'Image No Preview.jpg',
        file_type: 'image',
        preview_path: null,
      })
      const selection = createMockSelection()
      renderWithProviders(
        <MediaCanvas
          assets={[asset]}
          view="list"
          selection={selection}
        />
      )
      const img = screen.getByRole('img', { name: 'Image No Preview.jpg' })
      expect(img).toHaveAttribute('src', '/api/media/assets/img-no-preview/file')
    })

    it('renders video with preview_path using preview URL', () => {
      const asset = createMockAsset({
        id: 'vid-preview',
        name: 'Video With Preview.mp4',
        file_type: 'video',
        preview_path: '/path/to/preview.jpg',
      })
      const selection = createMockSelection()
      renderWithProviders(
        <MediaCanvas
          assets={[asset]}
          view="list"
          selection={selection}
        />
      )
      const img = screen.getByRole('img', { name: 'Video With Preview.mp4' })
      expect(img).toHaveAttribute('src', '/api/media/assets/vid-preview/preview')
    })

    it('renders video without preview_path as type label', () => {
      const asset = createMockAsset({
        id: 'vid-no-preview',
        name: 'Video No Preview.mp4',
        file_type: 'video',
        preview_path: null,
      })
      const selection = createMockSelection()
      renderWithProviders(
        <MediaCanvas
          assets={[asset]}
          view="list"
          selection={selection}
        />
      )
      const typeLabels = screen.getAllByText('video')
      const thumbnailLabel = typeLabels.find(
        (el) => el.classList.contains('text-xs') && el.classList.contains('text-muted-foreground')
      )
      expect(thumbnailLabel).toBeInTheDocument()
      expect(thumbnailLabel).toHaveClass('capitalize')
      const img = screen.queryByRole('img')
      expect(img).not.toBeInTheDocument()
    })
  })
})
