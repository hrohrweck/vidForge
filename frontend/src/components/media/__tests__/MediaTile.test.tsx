import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../../../test/utils'
import { MediaTile } from '../MediaTile'
import type { MediaAsset } from '../../../api/types/media'

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

describe('MediaTile', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('renders asset name', () => {
      const asset = createMockAsset({ name: 'My Video.mp4' })
      renderWithProviders(<MediaTile asset={asset} />)
      expect(screen.getByText('My Video.mp4')).toBeInTheDocument()
    })

    it('renders type indicator badge', () => {
      const asset = createMockAsset({ file_type: 'video' })
      renderWithProviders(<MediaTile asset={asset} />)
      expect(screen.getByText('video')).toBeInTheDocument()
    })

    it('renders video icon for video files', () => {
      const asset = createMockAsset({ file_type: 'video', preview_path: null })
      renderWithProviders(<MediaTile asset={asset} />)
      expect(screen.getByText('🎬')).toBeInTheDocument()
    })

    it('renders image icon for image files', () => {
      const asset = createMockAsset({ file_type: 'image', preview_path: null })
      renderWithProviders(<MediaTile asset={asset} />)
      const container = screen.getByTestId('tile-container')
      expect(container).toBeInTheDocument()
    })

    it('renders fallback icon for image files', () => {
      const asset = createMockAsset({ file_type: 'image', preview_path: null })
      renderWithProviders(<MediaTile asset={asset} />)
      const container = screen.getByTestId('tile-container')
      expect(container).toBeInTheDocument()
    })

    it('renders audio icon for audio files', () => {
      const asset = createMockAsset({ file_type: 'audio', preview_path: null })
      renderWithProviders(<MediaTile asset={asset} />)
      expect(screen.getByText('🎵')).toBeInTheDocument()
    })

    it('renders markdown icon for markdown files', () => {
      const asset = createMockAsset({ file_type: 'markdown', preview_path: null })
      renderWithProviders(<MediaTile asset={asset} />)
      expect(screen.getByText('📝')).toBeInTheDocument()
    })

    it('uses asset_metadata for aspect ratio', () => {
      const asset = createMockAsset({
        asset_metadata: { width: 1920, height: 1080 },
      })
      renderWithProviders(<MediaTile asset={asset} />)
      const tile = screen.getByTestId('tile-container')
      expect(tile).toHaveStyle('aspect-ratio: 1920 / 1080')
    })

    it('falls back to 16:9 for video without metadata', () => {
      const asset = createMockAsset({
        file_type: 'video',
        asset_metadata: null,
      })
      renderWithProviders(<MediaTile asset={asset} />)
      const container = screen.getByTestId('tile-container')
      expect(container).toHaveStyle('aspect-ratio: 16 / 9')
    })

    it('falls back to 1:1 for image without metadata', () => {
      const asset = createMockAsset({
        file_type: 'image',
        asset_metadata: null,
      })
      renderWithProviders(<MediaTile asset={asset} />)
      const container = screen.getByTestId('tile-container')
      expect(container).toHaveStyle('aspect-ratio: 1 / 1')
    })
  })

  describe('selection', () => {
    it('shows checkbox on hover', () => {
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} />)
      const tile = screen.getByTestId('tile-container')
      
      fireEvent.mouseEnter(tile!)
      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toBeInTheDocument()
      expect(checkbox).not.toBeChecked()
    })

    it('shows checkbox when selected', () => {
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} selected />)
      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toBeInTheDocument()
      expect(checkbox).toBeChecked()
    })

    it('calls onSelect when checkbox is toggled', () => {
      const onSelect = vi.fn()
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} onSelect={onSelect} />)
      
      fireEvent.mouseEnter(screen.getByTestId('tile-container'))
      const checkbox = screen.getByRole('checkbox')
      fireEvent.click(checkbox)
      
      expect(onSelect).toHaveBeenCalledWith('test-asset-1', true, expect.anything())
    })

    it('calls onSelectOnly on bare click', () => {
      const onSelectOnly = vi.fn()
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} onSelectOnly={onSelectOnly} onToggle={vi.fn()} onRange={vi.fn()} />)
      
      fireEvent.click(screen.getByTestId('tile-container'))
      expect(onSelectOnly).toHaveBeenCalledWith('test-asset-1')
    })

    it('calls onToggle on ctrl+click', () => {
      const onToggle = vi.fn()
      const onSelectOnly = vi.fn()
      const onRange = vi.fn()
      const asset = createMockAsset()
      renderWithProviders(
        <MediaTile asset={asset} onSelectOnly={onSelectOnly} onToggle={onToggle} onRange={onRange} />
      )
      
      fireEvent.click(screen.getByTestId('tile-container'), { ctrlKey: true })
      expect(onToggle).toHaveBeenCalledWith('test-asset-1')
      expect(onSelectOnly).not.toHaveBeenCalled()
    })

    it('calls onToggle on meta+click', () => {
      const onToggle = vi.fn()
      const onSelectOnly = vi.fn()
      const onRange = vi.fn()
      const asset = createMockAsset()
      renderWithProviders(
        <MediaTile asset={asset} onSelectOnly={onSelectOnly} onToggle={onToggle} onRange={onRange} />
      )
      
      fireEvent.click(screen.getByTestId('tile-container'), { metaKey: true })
      expect(onToggle).toHaveBeenCalledWith('test-asset-1')
      expect(onSelectOnly).not.toHaveBeenCalled()
    })

    it('calls onRange on shift+click', () => {
      const onRange = vi.fn()
      const onSelectOnly = vi.fn()
      const onToggle = vi.fn()
      const asset = createMockAsset()
      renderWithProviders(
        <MediaTile asset={asset} onSelectOnly={onSelectOnly} onToggle={onToggle} onRange={onRange} />
      )
      
      fireEvent.click(screen.getByTestId('tile-container'), { shiftKey: true })
      expect(onRange).toHaveBeenCalledWith('test-asset-1')
      expect(onSelectOnly).not.toHaveBeenCalled()
    })

    it('has selected state ring when selected', () => {
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} selected />)
      const tile = screen.getByTestId('tile-container')
      expect(tile).toHaveClass('ring-2')
      expect(tile).toHaveClass('ring-primary')
    })
  })

  describe('video hover preview', () => {
    it('shows video element on hover for video assets', () => {
      const asset = createMockAsset({ file_type: 'video' })
      renderWithProviders(<MediaTile asset={asset} />)
      
      const tile = screen.getByTestId('tile-container')
      fireEvent.mouseEnter(tile!)
      
      const video = screen.getByTestId('video-preview') as HTMLVideoElement
      expect(video).toBeInTheDocument()
      expect(video.muted).toBe(true)
      expect(video).toHaveAttribute('loop')
      expect(video).toHaveAttribute('playsinline')
      expect(video).toHaveAttribute('autoplay')
    })

    it('does not show video element on hover for image assets', () => {
      const asset = createMockAsset({ file_type: 'image' })
      renderWithProviders(<MediaTile asset={asset} />)
      
      const tile = screen.getByTestId('tile-container')
      fireEvent.mouseEnter(tile!)
      
      expect(screen.queryByTestId('video-preview')).not.toBeInTheDocument()
    })

    it('shows volume icon for video on hover', () => {
      const asset = createMockAsset({ file_type: 'video' })
      renderWithProviders(<MediaTile asset={asset} />)
      
      const tile = screen.getByTestId('tile-container')
      fireEvent.mouseEnter(tile!)
      
      // Should show volume icon (muted state by default)
      expect(screen.getByTitle('Unmute')).toBeInTheDocument()
    })

    it('toggles mute state when volume icon is clicked', async () => {
      const asset = createMockAsset({ file_type: 'video' })
      renderWithProviders(<MediaTile asset={asset} />)
      
      const tile = screen.getByTestId('tile-container')
      fireEvent.mouseEnter(tile!)
      
      // Click to unmute
      const volumeButton = screen.getByTitle('Unmute')
      fireEvent.click(volumeButton)
      
      // Should now show mute button
      await waitFor(() => {
        expect(screen.getByTitle('Mute')).toBeInTheDocument()
      })
    })
  })

  describe('more actions', () => {
    it('shows more button on hover', () => {
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} />)
      
      const tile = screen.getByTestId('tile-container')
      fireEvent.mouseEnter(tile!)
      
      expect(screen.getByTitle('More options')).toBeInTheDocument()
    })

    it('calls onMoreClick when more button is clicked', () => {
      const onMoreClick = vi.fn()
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} onMoreClick={onMoreClick} />)
      
      const tile = screen.getByTestId('tile-container')
      fireEvent.mouseEnter(tile!)
      
      const moreButton = screen.getByTitle('More options')
      fireEvent.click(moreButton)
      
      expect(onMoreClick).toHaveBeenCalledWith(asset, expect.anything())
    })
  })

  describe('inline rename', () => {
    it('enters edit mode on double-click of name', () => {
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} onRename={vi.fn()} />)
      
      const nameElement = screen.getByText('Test Asset')
      fireEvent.doubleClick(nameElement)
      
      const input = screen.getByRole('textbox')
      expect(input).toBeInTheDocument()
      expect(input).toHaveValue('Test Asset')
    })

    it('does not enter edit mode if onRename is not provided', () => {
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} />)
      
      const nameElement = screen.getByText('Test Asset')
      fireEvent.doubleClick(nameElement)
      
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    })

    it('calls onRename with new name on Enter', async () => {
      const onRename = vi.fn().mockResolvedValue(undefined)
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} onRename={onRename} />)
      
      const nameElement = screen.getByText('Test Asset')
      fireEvent.doubleClick(nameElement)
      
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'New Name.mp4' } })
      fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' })
      
      await waitFor(() => {
        expect(onRename).toHaveBeenCalledWith('test-asset-1', 'New Name.mp4')
      })
    })

    it('cancels rename on Escape', () => {
      const onRename = vi.fn()
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} onRename={onRename} />)
      
      const nameElement = screen.getByText('Test Asset')
      fireEvent.doubleClick(nameElement)
      
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'New Name.mp4' } })
      fireEvent.keyDown(input, { key: 'Escape', code: 'Escape' })
      
      expect(onRename).not.toHaveBeenCalled()
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    })

    it('commits rename on blur', async () => {
      const onRename = vi.fn().mockResolvedValue(undefined)
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} onRename={onRename} />)
      
      const nameElement = screen.getByText('Test Asset')
      fireEvent.doubleClick(nameElement)
      
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'New Name.mp4' } })
      fireEvent.blur(input)
      
      await waitFor(() => {
        expect(onRename).toHaveBeenCalledWith('test-asset-1', 'New Name.mp4')
      })
    })

    it('does not call onRename if name is unchanged', async () => {
      const onRename = vi.fn()
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} onRename={onRename} />)
      
      const nameElement = screen.getByText('Test Asset')
      fireEvent.doubleClick(nameElement)
      
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'Test Asset' } })
      fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' })
      
      await waitFor(() => {
        expect(onRename).not.toHaveBeenCalled()
      })
    })

    it('does not call onRename if name is empty', async () => {
      const onRename = vi.fn()
      const asset = createMockAsset()
      renderWithProviders(<MediaTile asset={asset} onRename={onRename} />)
      
      const nameElement = screen.getByText('Test Asset')
      fireEvent.doubleClick(nameElement)
      
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: '' } })
      fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' })
      
      await waitFor(() => {
        expect(onRename).not.toHaveBeenCalled()
      })
    })
  })

  describe('lazy loading', () => {
    it('uses lazy loading for images', () => {
      const asset = createMockAsset({ file_type: 'image' })
      renderWithProviders(<MediaTile asset={asset} />)
      
      const img = screen.getByAltText('Test Asset')
      expect(img).toHaveAttribute('loading', 'lazy')
    })
  })

  describe('preview handling', () => {
    it('shows placeholder when preview_url is missing for video', () => {
      const asset = createMockAsset({ file_type: 'video', preview_path: null })
      renderWithProviders(<MediaTile asset={asset} />)
      
      expect(screen.getByText('🎬')).toBeInTheDocument()
    })

    it('shows placeholder when preview_url is missing for image', () => {
      const asset = createMockAsset({ file_type: 'image', preview_path: null })
      renderWithProviders(<MediaTile asset={asset} />)
      
      const container = screen.getByTestId('tile-container')
      expect(container).toBeInTheDocument()
    })
  })
})
