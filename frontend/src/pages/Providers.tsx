import { FormEvent, useMemo, useState } from 'react'
import { isAxiosError } from 'axios'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, RefreshCw, Pencil, Trash2, Power, PowerOff, RotateCcw } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { Button } from '../components/ui/button'
import {
  Provider,
  ProviderCreateRequest,
  ProviderUpdateRequest,
  ProviderStatus,
  providersApi,
} from '../api/client'

interface ProviderFormState {
  id: string | null
  name: string
  providerType: 'comfyui_direct' | 'runpod' | 'poe'
  comfyuiUrl: string
  maxConcurrentJobs: string
  endpointId: string
  apiKey: string
  costPerGpuHour: string
  idleTimeout: string
  flashbootEnabled: boolean
  maxWorkers: string
  dailyBudget: string
  priority: string
  isActive: boolean
}

const getErrorMessage = (error: unknown): string => {
  if (isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail
    if (typeof detail === 'string' && detail) {
      return detail
    }

    if (typeof error.response?.data === 'string' && error.response.data) {
      return error.response.data
    }

    return `Request failed with status ${error.response?.status || 'unknown'}`
  }

  if (error instanceof Error && error.message) {
    return error.message
  }

  return 'An unexpected error occurred while saving provider.'
}

const defaultFormState: ProviderFormState = {
  id: null,
  name: '',
  providerType: 'comfyui_direct',
  comfyuiUrl: '',
  maxConcurrentJobs: '1',
  endpointId: '',
  apiKey: '',
  costPerGpuHour: '0.69',
  idleTimeout: '30',
  flashbootEnabled: true,
  maxWorkers: '3',
  dailyBudget: '',
  priority: '0',
  isActive: true,
}

export default function Providers() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useAuthStore()

  const [showForm, setShowForm] = useState(false)
  const [formState, setFormState] = useState<ProviderFormState>(defaultFormState)
  const [formBusy, setFormBusy] = useState(false)
  const [formError, setFormError] = useState('')
  const [actionError, setActionError] = useState('')

  const { data: providers, isLoading } = useQuery<Provider[]>({
    queryKey: ['providers'],
    queryFn: providersApi.list,
    enabled: user?.is_superuser,
  })

  const { data: statuses } = useQuery<ProviderStatus[]>({
    queryKey: ['provider-statuses'],
    queryFn: providersApi.getStatuses,
    enabled: user?.is_superuser,
    refetchInterval: 15000,
  })

  const statusLookup = useMemo(() => {
    const map = new Map<string, ProviderStatus>()
    statuses?.forEach((status) => {
      map.set(status.id, status)
    })
    return map
  }, [statuses])

  const createProvider = useMutation({
    mutationFn: async (data: ProviderCreateRequest) => {
      return providersApi.create(data)
    },
    onSuccess: () => {
      setActionError('')
      queryClient.invalidateQueries({ queryKey: ['providers'] })
      queryClient.invalidateQueries({ queryKey: ['provider-statuses'] })
      setShowForm(false)
      setFormState(defaultFormState)
    },
    onError: (error) => {
      setFormError(getErrorMessage(error))
    },
  })

  const updateProvider = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: ProviderUpdateRequest }) => {
      return providersApi.update(id, data)
    },
    onSuccess: () => {
      setActionError('')
      queryClient.invalidateQueries({ queryKey: ['providers'] })
      queryClient.invalidateQueries({ queryKey: ['provider-statuses'] })
      setShowForm(false)
      setFormState(defaultFormState)
    },
    onError: (error) => {
      setFormError(getErrorMessage(error))
    },
  })

  const deleteProvider = useMutation({
    mutationFn: async (id: string) => {
      await providersApi.delete(id)
    },
    onSuccess: () => {
      setActionError('')
      queryClient.invalidateQueries({ queryKey: ['providers'] })
      queryClient.invalidateQueries({ queryKey: ['provider-statuses'] })
    },
    onError: (error) => {
      setActionError(getErrorMessage(error))
    },
  })

  const resetSpend = useMutation({
    mutationFn: async (id: string) => {
      await providersApi.resetSpend(id)
    },
    onSuccess: () => {
      setActionError('')
      queryClient.invalidateQueries({ queryKey: ['providers'] })
      queryClient.invalidateQueries({ queryKey: ['provider-statuses'] })
    },
    onError: (error) => {
      setActionError(getErrorMessage(error))
    },
  })

  const toggleActive = useMutation({
    mutationFn: async ({ id, isActive }: { id: string; isActive: boolean }) => {
      return providersApi.update(id, { is_active: isActive })
    },
    onSuccess: () => {
      setActionError('')
      queryClient.invalidateQueries({ queryKey: ['providers'] })
      queryClient.invalidateQueries({ queryKey: ['provider-statuses'] })
    },
    onError: (error) => {
      setActionError(getErrorMessage(error))
    },
  })

  const setBudget = useMutation({
    mutationFn: async ({ id, value }: { id: string; value: number | null }) => {
      return providersApi.setBudget(id, value)
    },
    onSuccess: () => {
      setActionError('')
      queryClient.invalidateQueries({ queryKey: ['providers'] })
      queryClient.invalidateQueries({ queryKey: ['provider-statuses'] })
    },
    onError: (error) => {
      setActionError(getErrorMessage(error))
    },
  })

  if (!user?.is_superuser) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <p className="mb-4 text-red-600">Admin access is required.</p>
        <Button variant="outline" onClick={() => navigate('/')}>
          Back to Dashboard
        </Button>
      </div>
    )
  }

  const normalizeBudget = (value: string): number | null => {
    const trimmed = value.trim()
    if (!trimmed) return null
    const parsed = Number.parseFloat(trimmed)
    return Number.isFinite(parsed) ? parsed : null
  }

  const openCreate = () => {
    setFormError('')
    setActionError('')
    setFormState(defaultFormState)
    setShowForm(true)
  }

  const openEdit = (provider: Provider) => {
    const config = provider.config || {}
    const providerType = provider.provider_type
    const nextState: ProviderFormState = {
      id: provider.id,
      name: provider.name,
      providerType,
          comfyuiUrl:
            (typeof config.comfyui_url === 'string' && config.comfyui_url) || '',
      maxConcurrentJobs:
        (typeof config.max_concurrent_jobs === 'number' && String(config.max_concurrent_jobs)) ||
        '1',
      endpointId: (typeof config.endpoint_id === 'string' && config.endpoint_id) || '',
      apiKey: '',
      costPerGpuHour:
        (typeof config.cost_per_gpu_hour === 'number' && String(config.cost_per_gpu_hour)) || '0.69',
      idleTimeout:
        (typeof config.idle_timeout_seconds === 'number' && String(config.idle_timeout_seconds)) ||
        '30',
      flashbootEnabled:
        typeof config.flashboot_enabled === 'boolean' ? config.flashboot_enabled : true,
      maxWorkers:
        (typeof config.max_workers === 'number' && String(config.max_workers)) || '3',
      dailyBudget: provider.daily_budget_limit == null ? '' : String(provider.daily_budget_limit),
      priority: String(provider.priority || 0),
      isActive: provider.is_active,
    }
    setFormState(nextState)
    setFormError('')
    setActionError('')
    setShowForm(true)
  }

  const parseProviderPayload = () => {
    const dailyBudget = normalizeBudget(formState.dailyBudget)
    const payloadBase = {
      name: formState.name,
      daily_budget_limit: dailyBudget,
      priority: Number.parseInt(formState.priority, 10) || 0,
    }

    if (formState.providerType === 'comfyui_direct') {
      if (!formState.comfyuiUrl.trim()) {
        setFormError('ComfyUI URL is required for ComfyUI Direct provider')
        return
      }
      const payload: ProviderCreateRequest | ProviderUpdateRequest = {
        ...payloadBase,
        provider_type: 'comfyui_direct',
        config: {
          comfyui_url: formState.comfyuiUrl.trim(),
          max_concurrent_jobs:
            Number.parseInt(formState.maxConcurrentJobs, 10) > 0
              ? Number.parseInt(formState.maxConcurrentJobs, 10)
              : 1,
        },
      }
      return payload
    }

    if (formState.providerType === 'runpod') {
      const config: Record<string, unknown> = {
        endpoint_id: formState.endpointId,
        cost_per_gpu_hour:
          Number.parseFloat(formState.costPerGpuHour) > 0
            ? Number.parseFloat(formState.costPerGpuHour)
            : 0.69,
        idle_timeout_seconds:
          Number.parseInt(formState.idleTimeout, 10) > 0
            ? Number.parseInt(formState.idleTimeout, 10)
            : 30,
        flashboot_enabled: formState.flashbootEnabled,
        max_workers: Number.parseInt(formState.maxWorkers, 10) > 0
            ? Number.parseInt(formState.maxWorkers, 10)
            : 3,
      }

      const runpodPayload: ProviderCreateRequest | ProviderUpdateRequest = {
        ...payloadBase,
        provider_type: 'runpod',
        config: {
          ...config,
        },
      }

      if (formState.apiKey.trim()) {
        ;(runpodPayload as ProviderCreateRequest | ProviderUpdateRequest).config = {
          ...(runpodPayload.config as Record<string, unknown>),
          api_key: formState.apiKey.trim(),
        }
      }

      return runpodPayload
    }

    if (formState.providerType === 'poe') {
      const poePayload: ProviderCreateRequest | ProviderUpdateRequest = {
        ...payloadBase,
        provider_type: 'poe',
        config: {
          max_concurrent_jobs:
            Number.parseInt(formState.maxConcurrentJobs, 10) > 0
              ? Number.parseInt(formState.maxConcurrentJobs, 10)
              : 1,
        },
      }

      if (formState.apiKey.trim()) {
        poePayload.config = {
          ...poePayload.config,
          api_key: formState.apiKey.trim(),
        }
      }

      return poePayload
    }

    return null
  }

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setFormBusy(true)
    setFormError('')
    setActionError('')

    try {
      if (!formState.name.trim()) {
        setFormError('Provider name is required')
        return
      }

      if (formState.providerType === 'runpod' && !formState.endpointId.trim()) {
        setFormError('RunPod endpoint ID is required')
        return
      }

      if (
        formState.providerType === 'runpod' &&
        !formState.id &&
        !formState.apiKey.trim()
      ) {
        setFormError('RunPod API key is required for new providers')
        return
      }

      const payload = parseProviderPayload()

      if (formState.id) {
        await updateProvider.mutateAsync({
          id: formState.id,
          data: {
            ...(payload as ProviderUpdateRequest),
            is_active: formState.isActive,
          },
        })
      } else {
        await createProvider.mutateAsync(payload as ProviderCreateRequest)
      }
    } catch (error) {
      setFormError(getErrorMessage(error))
    } finally {
      setFormBusy(false)
    }
  }

  const openBudgetPrompt = (provider: Provider) => {
    setActionError('')
    const next = window.prompt(
      'Set daily budget. Leave empty to clear limit.',
      provider.daily_budget_limit == null ? '' : String(provider.daily_budget_limit)
    )
    if (next === null) {
      return
    }

    if (!next.trim()) {
      setBudget.mutate({ id: provider.id, value: null })
      return
    }

    const value = Number.parseFloat(next)
    if (Number.isNaN(value) || value < 0) {
      setActionError('Enter a valid non-negative number')
      return
    }

    setBudget.mutate({ id: provider.id, value })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Provider Management</h1>
          <p className="text-muted-foreground">Create and manage ComfyUI Direct or RunPod providers.</p>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={() => {
              setActionError('')
              queryClient.invalidateQueries({ queryKey: ['providers'] })
            }}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4 mr-2" />
            New Provider
          </Button>
        </div>
      </div>

      {actionError ? (
        <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md">{actionError}</div>
      ) : null}

      {isLoading ? (
        <p className="text-muted-foreground">Loading providers...</p>
      ) : (
        <div className="space-y-4">
          {providers && providers.length > 0 ? (
            providers.map((provider) => {
              const status = statusLookup.get(provider.id)
              return (
                <div key={provider.id} className="border rounded-lg p-5 space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-lg font-semibold">{provider.name}</p>
                      <p className="text-sm text-muted-foreground">Type: {provider.provider_type}</p>
                      <p className="text-sm text-muted-foreground">
                        Priority: {provider.priority} · Active:{' '}
                        <span className={provider.is_active ? 'text-green-700' : 'text-red-700'}>
                          {provider.is_active ? 'Yes' : 'No'}
                        </span>
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-1 rounded-full text-xs ${
                          status?.is_available ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {status?.is_available ? 'Available' : 'Unavailable'}
                      </span>
                      {status?.estimated_wait_seconds != null && (
                        <span className="px-2 py-1 rounded-full bg-secondary text-sm">
                          wait {status.estimated_wait_seconds}s
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Spend today: ${provider.current_daily_spend.toFixed(4)} / {provider.daily_budget_limit == null ? 'No limit' : `$${provider.daily_budget_limit.toFixed(4)}`} •
                    budget status: {status?.message || 'N/A'}
                  </p>
                  {status?.workers && (
                    <p className="text-xs text-muted-foreground">
                      Workers: total={status.workers.total}, online={status.workers.online}, busy={status.workers.busy}, offline={status.workers.offline}
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground">Message: {status?.message || 'No status data'}</p>

                  <div className="flex gap-2 flex-wrap">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setActionError('')
                        toggleActive.mutate({ id: provider.id, isActive: !provider.is_active })
                      }}
                    >
                      {provider.is_active ? (
                        <PowerOff className="h-4 w-4 mr-2" />
                      ) : (
                        <Power className="h-4 w-4 mr-2" />
                      )}
                      {provider.is_active ? 'Disable' : 'Enable'}
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => openEdit(provider)}
                    >
                      <Pencil className="h-4 w-4 mr-2" />
                      Edit
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => openBudgetPrompt(provider)}
                    >
                      <RotateCcw className="h-4 w-4 mr-2" />
                      Set Budget
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => resetSpend.mutate(provider.id)}
                    >
                      Reset Spend
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      className="text-red-600"
                      onClick={() => {
                        if (window.confirm(`Delete provider ${provider.name}?`)) {
                          setActionError('')
                          deleteProvider.mutate(provider.id)
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Delete
                    </Button>
                  </div>
                </div>
              )
            })
          ) : (
            <p className="text-muted-foreground">No providers found.</p>
          )}
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="w-full max-w-xl bg-background rounded-lg border p-6 max-h-[90vh] overflow-auto">
            <h2 className="text-xl font-semibold mb-4">
              {formState.id ? 'Edit Provider' : 'Create Provider'}
            </h2>

            {formError ? <div className="mb-4 p-3 text-sm text-destructive bg-destructive/10 rounded-md">{formError}</div> : null}

            <form className="space-y-4" onSubmit={onSubmit}>
              <div className="space-y-2">
                <label htmlFor="provider-name" className="text-sm font-medium">
                  Name
                </label>
                <input
                  id="provider-name"
                  className="w-full border rounded-md px-3 py-2"
                  value={formState.name}
                  onChange={(e) => setFormState((prev) => ({ ...prev, name: e.target.value }))}
                  required
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Provider Type</label>
                <div className="flex gap-4">
                  <label className="inline-flex items-center gap-2">
                    <input
                      type="radio"
                      checked={formState.providerType === 'comfyui_direct'}
                      onChange={() =>
                        setFormState((prev) => ({
                          ...prev,
                          providerType: 'comfyui_direct',
                          apiKey: '',
                        }))
                      }
                    />
                    ComfyUI Direct
                  </label>
                  <label className="inline-flex items-center gap-2">
                    <input
                      type="radio"
                      checked={formState.providerType === 'runpod'}
                      onChange={() =>
                        setFormState((prev) => ({
                          ...prev,
                          providerType: 'runpod',
                        }))
                      }
                    />
                    RunPod
                  </label>
                  <label className="inline-flex items-center gap-2">
                    <input
                      type="radio"
                      checked={formState.providerType === 'poe'}
                      onChange={() =>
                        setFormState((prev) => ({
                          ...prev,
                          providerType: 'poe',
                          apiKey: '',
                        }))
                      }
                    />
                    Poe
                  </label>
                </div>
              </div>

              {formState.providerType === 'comfyui_direct' ? (
                <>
                  <div className="space-y-2">
                    <label htmlFor="comfyui-url" className="text-sm font-medium">
                      ComfyUI URL
                    </label>
                    <input
                      id="comfyui-url"
                      className="w-full border rounded-md px-3 py-2"
                      value={formState.comfyuiUrl}
                      onChange={(e) =>
                        setFormState((prev) => ({
                          ...prev,
                          comfyuiUrl: e.target.value,
                        }))
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <label htmlFor="local-concurrent" className="text-sm font-medium">
                      Max Concurrent Jobs
                    </label>
                    <input
                      id="local-concurrent"
                      type="number"
                      className="w-full border rounded-md px-3 py-2"
                      value={formState.maxConcurrentJobs}
                      min={1}
                      onChange={(e) =>
                        setFormState((prev) => ({ ...prev, maxConcurrentJobs: e.target.value }))
                      }
                    />
                  </div>
                </>
              ) : (
                <>
                  <div className="space-y-2">
                    <label htmlFor="endpoint-id" className="text-sm font-medium">
                      RunPod Endpoint ID
                    </label>
                    <input
                      id="endpoint-id"
                      className="w-full border rounded-md px-3 py-2"
                      value={formState.endpointId}
                      onChange={(e) =>
                        setFormState((prev) => ({
                          ...prev,
                          endpointId: e.target.value,
                        }))
                      }
                      required={formState.providerType === 'runpod'}
                    />
                  </div>
                  <div className="space-y-2">
                    <label htmlFor="runpod-api-key" className="text-sm font-medium">
                      RunPod API Key {formState.id ? '(leave blank to keep current)' : ''}
                    </label>
                    <input
                      id="runpod-api-key"
                      type="password"
                      className="w-full border rounded-md px-3 py-2"
                      value={formState.apiKey}
                      placeholder={formState.id ? '••••••••' : ''}
                      onChange={(e) =>
                        setFormState((prev) => ({
                          ...prev,
                          apiKey: e.target.value,
                        }))
                      }
                    />
                    {!formState.apiKey && formState.id ? (
                      <p className="text-xs text-muted-foreground">Using existing API key.</p>
                    ) : null}
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="space-y-2">
                      <label htmlFor="runpod-cost" className="text-sm font-medium">
                        Cost per GPU Hour
                      </label>
                      <input
                        id="runpod-cost"
                        type="number"
                        step="0.01"
                        min="0"
                        className="w-full border rounded-md px-3 py-2"
                        value={formState.costPerGpuHour}
                        onChange={(e) =>
                          setFormState((prev) => ({
                            ...prev,
                            costPerGpuHour: e.target.value,
                          }))
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <label htmlFor="runpod-idle-timeout" className="text-sm font-medium">
                        Idle Timeout (sec)
                      </label>
                      <input
                        id="runpod-idle-timeout"
                        type="number"
                        min="1"
                        className="w-full border rounded-md px-3 py-2"
                        value={formState.idleTimeout}
                        onChange={(e) =>
                          setFormState((prev) => ({
                            ...prev,
                            idleTimeout: e.target.value,
                          }))
                        }
                      />
                    </div>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="space-y-2">
                      <label className="text-sm font-medium">Flashboot</label>
                      <label className="inline-flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={formState.flashbootEnabled}
                          onChange={(e) =>
                            setFormState((prev) => ({
                              ...prev,
                              flashbootEnabled: e.target.checked,
                            }))
                          }
                        />
                        Enable flashboot
                      </label>
                    </div>
                    <div className="space-y-2">
                      <label htmlFor="runpod-workers" className="text-sm font-medium">
                        Max Workers
                      </label>
                      <input
                        id="runpod-workers"
                        type="number"
                        min="1"
                        className="w-full border rounded-md px-3 py-2"
                        value={formState.maxWorkers}
                        onChange={(e) =>
                          setFormState((prev) => ({
                            ...prev,
                            maxWorkers: e.target.value,
                          }))
                        }
                      />
                    </div>
                  </div>
                </>
              ) : formState.providerType === 'poe' ? (
                <>
                  <div className="space-y-2">
                    <label htmlFor="poe-api-key" className="text-sm font-medium">
                      Poe API Key {formState.id ? '(leave blank to keep current)' : ''}
                    </label>
                    <input
                      id="poe-api-key"
                      type="password"
                      className="w-full border rounded-md px-3 py-2"
                      value={formState.apiKey}
                      placeholder={formState.id ? '••••••••' : ''}
                      onChange={(e) =>
                        setFormState((prev) => ({
                          ...prev,
                          apiKey: e.target.value,
                        }))
                      }
                    />
                    {!formState.apiKey && formState.id ? (
                      <p className="text-xs text-muted-foreground">Using existing API key.</p>
                    ) : null}
                  </div>
                  <div className="space-y-2">
                    <label htmlFor="poe-max-concurrent" className="text-sm font-medium">
                      Max Concurrent Jobs
                    </label>
                    <input
                      id="poe-max-concurrent"
                      type="number"
                      className="w-full border rounded-md px-3 py-2"
                      value={formState.maxConcurrentJobs}
                      min={1}
                      onChange={(e) =>
                        setFormState((prev) => ({ ...prev, maxConcurrentJobs: e.target.value }))
                      }
                    />
                  </div>
                </>
              ) : null}

              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <label htmlFor="provider-budget" className="text-sm font-medium">
                    Daily Budget Limit
                  </label>
                  <input
                    id="provider-budget"
                    type="number"
                    step="0.01"
                    min="0"
                    className="w-full border rounded-md px-3 py-2"
                    value={formState.dailyBudget}
                    onChange={(e) =>
                      setFormState((prev) => ({ ...prev, dailyBudget: e.target.value }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <label htmlFor="provider-priority" className="text-sm font-medium">
                    Priority
                  </label>
                  <input
                    id="provider-priority"
                    type="number"
                    className="w-full border rounded-md px-3 py-2"
                    value={formState.priority}
                    onChange={(e) =>
                      setFormState((prev) => ({ ...prev, priority: e.target.value }))
                    }
                  />
                </div>
              </div>

              {formState.id && (
                <div className="inline-flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="provider-active"
                    checked={formState.isActive}
                    onChange={(e) =>
                      setFormState((prev) => ({ ...prev, isActive: e.target.checked }))
                    }
                  />
                  <label htmlFor="provider-active">Active</label>
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2">
                <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setFormError('')
                      setActionError('')
                      setShowForm(false)
                      setFormState(defaultFormState)
                    }}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={formBusy}>
                  {formBusy ? <RefreshCw className="h-4 w-4 animate-spin mr-2" /> : null}
                  Save Provider
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
