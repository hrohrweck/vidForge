import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent, waitFor, prettyDOM } from '@testing-library/react'
import { renderWithProviders } from '../../test/utils'
import QuickCreateMedia from '../../components/QuickCreateMedia'
import { modelsApi } from '../../api/client'

vi.mock('../../api/client', () => ({
  default: { post: vi.fn().mockResolvedValue({ data: {} }) },
  modelsApi: {
    getAvailableModels: vi.fn().mockResolvedValue({
      image_models: [{ id: 'img-1', name: 'SDXL Turbo', description: 'Fast', size_gb: 1.5, speed: 'fast', quality: 'high', license: 'open', provider: 'comfyui_direct', default: true, capabilities: { accepts_text: true } }],
      video_models: [],
      text_models: [],
    }),
  },
}))

describe('Debug QuickCreateMedia', () => {
  it('debug DOM', async () => {
    renderWithProviders(<QuickCreateMedia />)
    fireEvent.click(screen.getByRole('button', { name: /create media/i }))
    
    // Wait for the query to resolve
    await waitFor(() => {
      expect(modelsApi.getAvailableModels).toHaveBeenCalled()
    })
    
    // Give React time to re-render
    await new Promise(r => setTimeout(r, 100))
    
    console.log('=== BODY ===')
    console.log(prettyDOM(document.body, 10000))
  })
})
