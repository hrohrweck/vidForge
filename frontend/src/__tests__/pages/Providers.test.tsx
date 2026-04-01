import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import Providers from '../../pages/Providers'
import { renderWithProviders } from '../../test/utils'
import { server } from '../../test/mocks/server'

describe('Providers Page', () => {
  beforeEach(() => {
    server.resetHandlers()

    server.use(
      http.get('*/api/providers', () => {
        return HttpResponse.json([
          {
            id: 'provider-local-1',
            name: 'Local ComfyUI',
            provider_type: 'local',
            config: {
              comfyui_url: 'http://localhost:8188',
              max_concurrent_jobs: 1,
            },
            is_active: true,
            daily_budget_limit: 50,
            current_daily_spend: 12.34,
            priority: 0,
            created_at: '2024-01-01T00:00:00Z',
          },
          {
            id: 'provider-runpod-1',
            name: 'RunPod Primary',
            provider_type: 'runpod',
            config: {
              endpoint_id: 'endpoint-id',
              cost_per_gpu_hour: 0.7,
              idle_timeout_seconds: 30,
              flashboot_enabled: true,
              max_workers: 3,
            },
            is_active: false,
            daily_budget_limit: null,
            current_daily_spend: 0,
            priority: 1,
            created_at: '2024-01-01T00:00:00Z',
          },
        ])
      }),
      http.get('*/api/providers/status', () => {
        return HttpResponse.json([
          {
            id: 'provider-local-1',
            name: 'Local ComfyUI',
            type: 'local',
            is_available: true,
            estimated_wait_seconds: 0,
            message: 'Ready',
            workers: {
              total: 1,
              online: 1,
              busy: 0,
              offline: 0,
            },
            daily_budget_limit: 50,
            current_daily_spend: 12.34,
          },
          {
            id: 'provider-runpod-1',
            name: 'RunPod Primary',
            type: 'runpod',
            is_available: false,
            estimated_wait_seconds: 99,
            message: 'Starting',
            workers: {
              total: 0,
              online: 0,
              busy: 0,
              offline: 0,
            },
            daily_budget_limit: null,
            current_daily_spend: 0,
          },
        ])
      })
    )
  })

  it('blocks non-admin access', () => {
    renderWithProviders(<Providers />, { superuser: false })

    expect(screen.getByText('Admin access is required.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /back to dashboard/i })).toBeInTheDocument()
  })

  it('renders provider list for admins', async () => {
    renderWithProviders(<Providers />, { superuser: true })

    expect(await screen.findByText('Provider Management')).toBeInTheDocument()
    expect(await screen.findByText('Local ComfyUI')).toBeInTheDocument()
    expect(await screen.findByText('RunPod Primary')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /edit/i })).toHaveLength(2)
  })

  it('submits provider create payload for local provider', async () => {
    const user = userEvent.setup()
    let capturedBody: Record<string, unknown> | null = null

    server.use(
      http.post('*/api/providers', async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          {
            id: 'provider-created',
            name: (capturedBody.name as string) || 'New Provider',
            provider_type: 'local',
            config: (capturedBody.config as Record<string, unknown>) || {},
            is_active: true,
            daily_budget_limit: 50,
            current_daily_spend: 0,
            priority: (capturedBody.priority as number) || 0,
            created_at: '2024-01-02T00:00:00Z',
          },
          { status: 201 }
        )
      })
    )

    renderWithProviders(<Providers />, { superuser: true })
    await user.click(screen.getByRole('button', { name: /new provider/i }))

    await user.type(screen.getByLabelText('Name'), 'New Local Provider')
    await user.type(screen.getByLabelText('ComfyUI URL'), 'http://127.0.0.1:8188')

    await user.click(screen.getByRole('button', { name: /save provider/i }))

    await waitFor(() => {
      expect(capturedBody).not.toBeNull()
      expect(capturedBody).toMatchObject({
        name: 'New Local Provider',
        provider_type: 'local',
      })
    })
  })

  it('displays create provider errors from API response', async () => {
    const user = userEvent.setup()

    server.use(
      http.post('*/api/providers', () => {
        return HttpResponse.json(
          { detail: 'Provider with this name already exists' },
          { status: 400 }
        )
      })
    )

    renderWithProviders(<Providers />, { superuser: true })
    await user.click(screen.getByRole('button', { name: /new provider/i }))

    await user.type(screen.getByLabelText('Name'), 'Existing Provider')
    await user.click(screen.getByRole('button', { name: /save provider/i }))

    expect(
      await screen.findByText('Provider with this name already exists')
    ).toBeInTheDocument()
  })

  it('does not send API key when editing runpod provider with blank key', async () => {
    const user = userEvent.setup()
    let capturedBody: Record<string, unknown> | null = null

    server.resetHandlers()
    server.use(
      http.get('*/api/providers', () => {
        return HttpResponse.json([
          {
            id: 'provider-runpod-1',
            name: 'RunPod Primary',
            provider_type: 'runpod',
            config: {
              endpoint_id: 'endpoint-id',
              cost_per_gpu_hour: 0.7,
              idle_timeout_seconds: 30,
              flashboot_enabled: true,
              max_workers: 3,
            },
            is_active: false,
            daily_budget_limit: null,
            current_daily_spend: 0,
            priority: 1,
            created_at: '2024-01-01T00:00:00Z',
          },
        ])
      }),
      http.patch('*/api/providers/:id', async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          id: 'provider-runpod-1',
          name: 'RunPod Primary',
          provider_type: 'runpod',
          config: (capturedBody?.config as Record<string, unknown>) || {},
          is_active: true,
          daily_budget_limit: null,
          current_daily_spend: 0,
          priority: 0,
          created_at: '2024-01-01T00:00:00Z',
        })
      }),
      http.get('*/api/providers/status', () => {
        return HttpResponse.json([
          {
            id: 'provider-runpod-1',
            name: 'RunPod Primary',
            type: 'runpod',
            is_available: true,
            estimated_wait_seconds: 0,
            message: 'Ready',
            workers: {
              total: 1,
              online: 1,
              busy: 0,
              offline: 0,
            },
            daily_budget_limit: null,
            current_daily_spend: 0,
          },
        ])
      })
    )

    renderWithProviders(<Providers />, { superuser: true })
    await user.click(await screen.findByRole('button', { name: /edit/i }))

    await user.click(screen.getByRole('button', { name: /save provider/i }))

    expect(await screen.findByRole('button', { name: /set budget/i })).toBeInTheDocument()
    await waitFor(() => {
      expect(capturedBody).not.toBeNull()
      const config = (capturedBody as { config?: Record<string, unknown> } | null)?.config
      expect(typeof config).toBe('object')
      expect(config).not.toBeNull()
      expect(Object.prototype.hasOwnProperty.call(config || {}, 'api_key')).toBe(false)
    })
  })

  it('shows an error when a provider action fails', async () => {
    const user = userEvent.setup()

    server.use(
      http.patch('*/api/providers/:id', () => {
        return HttpResponse.json(
          { detail: 'Provider update is not allowed right now' },
          { status: 403 }
        )
      })
    )

    renderWithProviders(<Providers />, { superuser: true })

    const disableButton = await screen.findByRole('button', { name: /disable/i })
    await user.click(disableButton)

    expect(
      await screen.findByText('Provider update is not allowed right now')
    ).toBeInTheDocument()
  })

  it('shows an error when budget prompt input is invalid', async () => {
    const user = userEvent.setup()

    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('-1')

    renderWithProviders(<Providers />, { superuser: true })

    const setBudgetButton = (await screen.findAllByRole('button', { name: /set budget/i })).at(0)
    expect(setBudgetButton).not.toBeNull()
    if (setBudgetButton) {
      await user.click(setBudgetButton)
    }

    expect(await screen.findByText('Enter a valid non-negative number')).toBeInTheDocument()

    promptSpy.mockRestore()
  })
})
