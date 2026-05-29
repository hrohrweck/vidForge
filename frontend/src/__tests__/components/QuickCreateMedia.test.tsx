import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../../test/utils'
import QuickCreateMedia from '../../components/QuickCreateMedia'
import api, { modelsApi } from '../../api/client'

vi.mock('../../api/client', () => ({
  default: {
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
  modelsApi: {
    getAvailableModels: vi.fn().mockResolvedValue({
      image_models: [
        {
          id: 'img-1',
          name: 'SDXL Turbo',
          description: 'Fast image generation',
          size_gb: 1.5,
          speed: 'fast',
          quality: 'high',
          license: 'open',
          provider: 'comfyui_direct',
          default: true,
          capabilities: { accepts_text: true },
        },
        {
          id: 'img-2',
          name: 'Flux Schnell',
          description: 'High quality image model',
          size_gb: 2.0,
          speed: 'medium',
          quality: 'high',
          license: 'open',
          provider: 'comfyui_direct',
          default: false,
          capabilities: { accepts_text: true },
        },
      ],
      video_models: [
        {
          id: 'vid-1',
          name: 'Wan Video',
          description: 'Video generation model',
          size_gb: 5.0,
          speed: 'slow',
          quality: 'high',
          license: 'open',
          provider: 'video',
          default: false,
          capabilities: { accepts_text: true },
        },
      ],
      text_models: [],
    }),
  },
}))

describe('QuickCreateMedia', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders trigger button', () => {
    renderWithProviders(<QuickCreateMedia />)
    expect(screen.getByRole('button', { name: /create media/i })).toBeInTheDocument()
  })

  it('opens modal on button click', async () => {
    renderWithProviders(<QuickCreateMedia />)
    fireEvent.click(screen.getByRole('button', { name: /create media/i }))

    await waitFor(() => {
      expect(screen.getByText('Image Models')).toBeInTheDocument()
    })
    expect(screen.getByText('Video Models')).toBeInTheDocument()
  })

  it('model list renders in modal', async () => {
    renderWithProviders(<QuickCreateMedia />)
    fireEvent.click(screen.getByRole('button', { name: /create media/i }))

    await waitFor(() => {
      expect(screen.getByText('SDXL Turbo')).toBeInTheDocument()
    })
    expect(screen.getByText('Flux Schnell')).toBeInTheDocument()
  })

  it('settings show after model selection', async () => {
    renderWithProviders(<QuickCreateMedia />)
    fireEvent.click(screen.getByRole('button', { name: /create media/i }))

    await waitFor(() => {
      expect(screen.getByText('SDXL Turbo')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('SDXL Turbo'))

    await waitFor(() => {
      expect(screen.getByText('Aspect Ratio')).toBeInTheDocument()
    })
    expect(
      screen.getByPlaceholderText('Describe what you want to generate...'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /generate/i })).toBeInTheDocument()
  })

  it('submit calls API and closes modal', async () => {
    renderWithProviders(<QuickCreateMedia />)
    fireEvent.click(screen.getByRole('button', { name: /create media/i }))

    await waitFor(() => {
      expect(screen.getByText('SDXL Turbo')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('SDXL Turbo'))

    const promptInput = await screen.findByPlaceholderText(
      'Describe what you want to generate...',
    )
    fireEvent.change(promptInput, {
      target: { value: 'A beautiful landscape' },
    })

    fireEvent.click(screen.getByRole('button', { name: /generate/i }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/media/generate',
        expect.objectContaining({
          model_id: 'img-1',
          prompt: 'A beautiful landscape',
          aspect_ratio: '1:1',
        }),
      )
    })

    await waitFor(() => {
      expect(screen.queryByText('Image Models')).not.toBeInTheDocument()
    })
  })

  it('back button returns to model selection', async () => {
    renderWithProviders(<QuickCreateMedia />)
    fireEvent.click(screen.getByRole('button', { name: /create media/i }))

    await waitFor(() => {
      expect(screen.getByText('SDXL Turbo')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('SDXL Turbo'))

    await waitFor(() => {
      expect(screen.getByText(/back to model selection/i)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText(/back to model selection/i))

    await waitFor(() => {
      expect(screen.getByText('Image Models')).toBeInTheDocument()
      expect(screen.getByText('SDXL Turbo')).toBeInTheDocument()
    })
  })

  it('shows image upload for image-to-image capable models', async () => {
    vi.mocked(modelsApi.getAvailableModels).mockResolvedValue({
      image_models: [
        {
          id: 'img-i2i',
          name: 'Image-to-Image Model',
          description: 'Supports image input',
          size_gb: 2.0,
          speed: 'fast',
          quality: 'high',
          license: 'open',
          provider: 'comfyui_direct',
          default: false,
          capabilities: { accepts_image: true },
        },
      ],
      video_models: [],
      text_models: [],
    })

    renderWithProviders(<QuickCreateMedia />)
    fireEvent.click(screen.getByRole('button', { name: /create media/i }))

    await waitFor(() => {
      expect(screen.getByText('Image-to-Image Model')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Image-to-Image Model'))

    await waitFor(() => {
      expect(screen.getByText(/reference image/i)).toBeInTheDocument()
    })

    expect(screen.getByText(/image is required/i)).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('Describe what you want to generate...')).toBeNull()
  })

  it('hides image upload for text-only models without image-to-image capability', async () => {
    vi.mocked(modelsApi.getAvailableModels).mockResolvedValue({
      image_models: [
        {
          id: 'img-text-only',
          name: 'Text-Only Image Model',
          description: 'Only supports text-to-image',
          size_gb: 1.5,
          speed: 'fast',
          quality: 'high',
          license: 'open',
          provider: 'comfyui_direct',
          default: false,
          capabilities: { accepts_text: true },
        },
      ],
      video_models: [],
      text_models: [],
    })

    renderWithProviders(<QuickCreateMedia />)
    fireEvent.click(screen.getByRole('button', { name: /create media/i }))

    await waitFor(() => {
      expect(screen.getByText('Text-Only Image Model')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Text-Only Image Model'))

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Describe what you want to generate...')).toBeInTheDocument()
    })

    expect(screen.queryByText(/reference image/i)).toBeNull()
  })

  it('shows both image upload and prompt for multimodal models', async () => {
    vi.mocked(modelsApi.getAvailableModels).mockResolvedValue({
      image_models: [
        {
          id: 'img-multi',
          name: 'Multimodal Model',
          description: 'Accepts both text and image',
          size_gb: 3.0,
          speed: 'medium',
          quality: 'high',
          license: 'open',
          provider: 'comfyui_direct',
          default: false,
          capabilities: { accepts_text: true, accepts_image: true },
        },
      ],
      video_models: [],
      text_models: [],
    })

    renderWithProviders(<QuickCreateMedia />)
    fireEvent.click(screen.getByRole('button', { name: /create media/i }))

    await waitFor(() => {
      expect(screen.getByText('Multimodal Model')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Multimodal Model'))

    await waitFor(() => {
      expect(screen.getByText(/reference image/i)).toBeInTheDocument()
    })

    expect(screen.getByText(/reference image \(optional\)/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Describe what you want to generate...')).toBeInTheDocument()
  })
})
