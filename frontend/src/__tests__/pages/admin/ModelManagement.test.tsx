import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import ModelManagement from '../../../pages/admin/ModelManagement'
import { renderWithProviders } from '../../../test/utils'
import { server } from '../../../test/mocks/server'

const mockProviders = [
  {
    id: 'provider-1',
    name: 'Local ComfyUI',
    provider_type: 'comfyui_direct',
    config: { comfyui_url: 'http://localhost:8188' },
    is_active: true,
    daily_budget_limit: 50,
    current_daily_spend: 0,
    priority: 0,
    created_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'provider-2',
    name: 'RunPod GPU',
    provider_type: 'runpod',
    config: { endpoint_id: 'ep-123' },
    is_active: true,
    daily_budget_limit: null,
    current_daily_spend: 0,
    priority: 1,
    created_at: '2024-01-01T00:00:00Z',
  },
]

const mockConfigs = [
  {
    id: 'config-1',
    providerId: 'provider-1',
    modelId: 'qwen-3.6',
    providerModelId: 'qwen-3.6',
    displayName: 'Qwen 3.6',
    modality: 'text',
    promptFormat: 'string',
    endpointType: 'llm',
    isActive: true,
    isDeprecated: false,
    lastSyncedAt: '2024-06-01T12:00:00Z',
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-06-01T12:00:00Z',
  },
  {
    id: 'config-2',
    providerId: 'provider-1',
    modelId: 'flux-schnell',
    providerModelId: 'flux.1-schnell',
    displayName: 'Flux Schnell',
    modality: 'image',
    promptFormat: 'string',
    endpointType: 'text_to_image',
    isActive: true,
    isDeprecated: false,
    lastSyncedAt: null,
    createdAt: '2024-02-01T00:00:00Z',
    updatedAt: '2024-02-01T00:00:00Z',
  },
  {
    id: 'config-3',
    providerId: 'provider-2',
    modelId: 'wan-2.2',
    providerModelId: 'wan-2.2-t2v',
    displayName: 'Wan 2.2',
    modality: 'video',
    promptFormat: 'string',
    endpointType: 'text_to_video',
    isActive: false,
    isDeprecated: true,
    lastSyncedAt: '2024-05-15T08:00:00Z',
    createdAt: '2024-03-01T00:00:00Z',
    updatedAt: '2024-05-15T08:00:00Z',
  },
]

describe('ModelManagement Page', () => {
  beforeEach(() => {
    server.resetHandlers()

    server.use(
      http.get('*/api/providers', () => HttpResponse.json(mockProviders)),

      http.get('*/api/admin/model-configs', ({ request }) => {
        const url = new URL(request.url)
        const modality = url.searchParams.get('modality')
        let filtered = [...mockConfigs]
        if (modality) {
          filtered = filtered.filter((c) => c.modality === modality)
        }
        return HttpResponse.json(filtered)
      }),

      http.post('*/api/admin/model-configs/:providerId/sync', () => {
        return HttpResponse.json({ status: 'ok', provider: 'provider-1' })
      }),

      http.put('*/api/admin/model-configs/:id', async ({ request, params }) => {
        const body = (await request.json()) as Record<string, unknown>
        const config = mockConfigs.find((c) => c.id === params.id)
        return HttpResponse.json({ ...config, ...body })
      }),

      http.delete('*/api/admin/model-configs/:id', () => {
        return HttpResponse.json({ ok: true })
      }),
    )
  })

  it('renders table with model rows from mocked API', async () => {
    renderWithProviders(<ModelManagement />, { superuser: true })

    expect(await screen.findByText('Model Management')).toBeInTheDocument()
    const qwenEls = await screen.findAllByText('qwen-3.6')
    expect(qwenEls.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('flux-schnell')).toBeInTheDocument()
    expect(screen.getByText('wan-2.2')).toBeInTheDocument()
    expect(screen.getByText('Qwen 3.6')).toBeInTheDocument()
    expect(screen.getByText('Flux Schnell')).toBeInTheDocument()
    expect(screen.getByText('Wan 2.2')).toBeInTheDocument()
    expect(screen.getByText('text')).toBeInTheDocument()
    expect(screen.getByText('image')).toBeInTheDocument()
    expect(screen.getByText('video')).toBeInTheDocument()
    const providerEls = await screen.findAllByText('Local ComfyUI')
    expect(providerEls.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('RunPod GPU')).toBeInTheDocument()
    expect(screen.getAllByLabelText('Edit model')).toHaveLength(3)
    expect(screen.getAllByLabelText('Delete model')).toHaveLength(3)
  })

  it('shows empty state when no models', async () => {
    server.use(
      http.get('*/api/admin/model-configs', () => HttpResponse.json([])),
    )

    renderWithProviders(<ModelManagement />, { superuser: true })

    await waitFor(() => {
      expect(screen.getByText('No model configurations found.')).toBeInTheDocument()
    })

    expect(
      screen.getByText('Configure a provider and sync models to populate this table.'),
    ).toBeInTheDocument()
  })

  it('filters by modality when selected', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ModelManagement />, { superuser: true })

    expect(await screen.findByText('Qwen 3.6')).toBeInTheDocument()

    const triggers = screen.getAllByRole('combobox')
    const modalityTrigger = triggers.find((el) =>
      el.textContent?.includes('All modalities')
    )
    if (!modalityTrigger) throw new Error('Modality filter not found')
    await user.click(modalityTrigger)

    const imageOption = await screen.findByRole('option', { name: 'Image' })
    await user.click(imageOption)

    await waitFor(() => {
      expect(screen.queryByText('Qwen 3.6')).not.toBeInTheDocument()
    })
    expect(screen.getByText('Flux Schnell')).toBeInTheDocument()
  })

  it('sync button triggers API call', async () => {
    let syncCalled = false
    let syncedProviderId = ''

    server.use(
      http.post('*/api/admin/model-configs/:providerId/sync', ({ params }) => {
        syncCalled = true
        syncedProviderId = params.providerId as string
        return HttpResponse.json({ status: 'ok' })
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<ModelManagement />, { superuser: true })

    await waitFor(() => {
      expect(screen.getByText('Model Management')).toBeInTheDocument()
    })

    const triggers = screen.getAllByRole('combobox')
    const syncTrigger = triggers.find((el) =>
      el.textContent?.includes('Select provider')
    )
    if (!syncTrigger) throw new Error('Sync provider select not found')
    await user.click(syncTrigger)

    const providerOption = await screen.findByRole('option', { name: 'Local ComfyUI' })
    await user.click(providerOption)

    const syncButton = screen.getByRole('button', { name: /^sync$/i })
    await user.click(syncButton)

    await waitFor(() => {
      expect(syncCalled).toBe(true)
      expect(syncedProviderId).toBe('provider-1')
    })
  })

  it('edit modal opens with pre-filled data', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ModelManagement />, { superuser: true })

    expect(await screen.findByText('Qwen 3.6')).toBeInTheDocument()

    const editButtons = screen.getAllByLabelText('Edit model')
    await user.click(editButtons[0])

    expect(await screen.findByText('Edit Model Configuration')).toBeInTheDocument()
    expect(screen.getByText(/Editing: qwen-3\.6/)).toBeInTheDocument()

    const displayNameInput = screen.getByDisplayValue('Qwen 3.6')
    expect(displayNameInput).not.toBeDisabled()
  })

  it('delete confirmation triggers API call', async () => {
    let deleteCalled = false
    let deletedId = ''

    server.use(
      http.delete('*/api/admin/model-configs/:id', ({ params }) => {
        deleteCalled = true
        deletedId = params.id as string
        return HttpResponse.json({ ok: true })
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<ModelManagement />, { superuser: true })

    expect(await screen.findByText('Qwen 3.6')).toBeInTheDocument()

    const deleteBtns = screen.getAllByLabelText('Delete model')
    await user.click(deleteBtns[0])

    expect(await screen.findByText('Delete Model Configuration')).toBeInTheDocument()

    const confirmBtn = screen.getByRole('button', { name: /^delete$/i })
    await user.click(confirmBtn)

    await waitFor(() => {
      expect(deleteCalled).toBe(true)
      expect(deletedId).toBe('config-1')
    })
  })
})
