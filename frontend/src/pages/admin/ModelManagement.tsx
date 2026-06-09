import { useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import {
  Search,
  Plus,
  RefreshCw,
  Trash2,
  Pencil,
} from 'lucide-react'
import {
  adminModelConfigsApi,
  type ModelConfig,
  type CreateModelConfigRequest,
  type UpdateModelConfigRequest,
} from '../../api/adminModelConfigs'
import { providersApi, type Provider } from '../../api/client'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../../components/ui/table'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'
import { Textarea } from '../../components/ui/textarea'
import { Switch } from '../../components/ui/switch'
import { toast } from '../../hooks/use-toast'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../components/ui/dialog'

const MODALITY_OPTIONS = ['text', 'image', 'video'] as const
const CAPABILITY_OPTIONS = [
  'text_to_image',
  'image_to_image',
  'text_to_video',
  'image_to_video',
] as const
const PROMPT_FORMATS = ['string', 'array'] as const
const ENDPOINT_TYPES = [
  'llm',
  'text_to_image',
  'image_to_video',
  'text_to_video',
  'image',
  'video',
] as const
const PAGE_SIZE = 20

const getErrorMessage = (error: unknown): string => {
  if (isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)
      ?.detail
    if (typeof detail === 'string' && detail) return detail
    if (typeof error.response?.data === 'string' && error.response.data)
      return error.response.data
    return `Request failed with status ${error.response?.status || 'unknown'}`
  }
  if (error instanceof Error && error.message) return error.message
  return 'An unexpected error occurred.'
}

const tryParseJson = (
  raw: string
): Record<string, unknown> | null => {
  try {
    const parsed = JSON.parse(raw)
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
    return null
  } catch {
    return null
  }
}

const jsonToPretty = (value: Record<string, unknown> | undefined): string =>
  value ? JSON.stringify(value, null, 2) : ''

// ─── Form types ───────────────────────────────────────────
interface ModelFormState {
  providerId: string
  modelId: string
  providerModelId: string
  displayName: string
  modality: string
  promptFormat: string
  endpointType: string
  parameterMap: string
  extraParams: string
  capabilities: string
  constraints: string
  costConfig: string
  comfyuiWorkflow: string
  isActive: boolean
  isChatEnabled: boolean
  isDeprecated: boolean
}

const configToFormState = (c: ModelConfig): ModelFormState => ({
  providerId: c.providerId,
  modelId: c.modelId,
  providerModelId: c.providerModelId,
  displayName: c.displayName,
  modality: c.modality,
  promptFormat: c.promptFormat,
  endpointType: c.endpointType,
  parameterMap: jsonToPretty(c.parameterMap),
  extraParams: jsonToPretty(c.extraParams as Record<string, unknown> | undefined),
  capabilities: jsonToPretty(c.capabilities as Record<string, unknown> | undefined),
  constraints: jsonToPretty(c.constraints as Record<string, unknown> | undefined),
  costConfig: jsonToPretty(c.costConfig as Record<string, unknown> | undefined),
  comfyuiWorkflow: c.comfyuiWorkflow ?? '',
  isActive: c.isActive,
  isChatEnabled: c.isChatEnabled,
  isDeprecated: c.isDeprecated,
})

const defaultFormState: ModelFormState = {
  providerId: '',
  modelId: '',
  providerModelId: '',
  displayName: '',
  modality: 'text',
  promptFormat: 'string',
  endpointType: 'llm',
  parameterMap: '',
  extraParams: '',
  capabilities: '',
  constraints: '',
  costConfig: '',
  comfyuiWorkflow: '',
  isActive: true,
  isChatEnabled: true,
  isDeprecated: false,
}

// ─── Component ────────────────────────────────────────────
export default function ModelManagement() {
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const providerParam = searchParams.get('provider')

  // ── Filters & search ──
  const [providerFilter, setProviderFilter] = useState<string>(providerParam || 'all')
  const [modalityFilter, setModalityFilter] = useState<string>('all')
  const [capabilityFilter, setCapabilityFilter] = useState<string>('all')
  const [activeFilter, setActiveFilter] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  // ── Sync state ──
  const [syncProvider, setSyncProvider] = useState<string>('')
  const [syncBusy, setSyncBusy] = useState(false)
  const [actionError, setActionError] = useState('')

  // ── Dialog state ──
  const [dialogOpen, setDialogOpen] = useState(false)
  const [isCreate, setIsCreate] = useState(false)
  const [editingConfig, setEditingConfig] = useState<ModelConfig | null>(null)
  const [formState, setFormState] = useState<ModelFormState>(defaultFormState)
  const [formBusy, setFormBusy] = useState(false)
  const [formError, setFormError] = useState('')

  // ── Delete state ──
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<ModelConfig | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  // ── Inline edit state ──
  const [editingNameId, setEditingNameId] = useState<string | null>(null)
  const [editingNameValue, setEditingNameValue] = useState('')
  const editInputRef = useRef<HTMLInputElement>(null)

  // ── Queries ──
  const { data: providers } = useQuery<Provider[]>({
    queryKey: ['providers'],
    queryFn: providersApi.list,
  })

  const { data: configs, isLoading } = useQuery<ModelConfig[]>({
    queryKey: ['admin-model-configs', providerFilter, modalityFilter, capabilityFilter, activeFilter],
    queryFn: () =>
      adminModelConfigsApi.list({
        providerId: providerFilter !== 'all' ? providerFilter : undefined,
        modality: modalityFilter !== 'all' ? modalityFilter : undefined,
        capability: capabilityFilter !== 'all' ? capabilityFilter : undefined,
        isActive: activeFilter !== 'all' ? activeFilter === 'active' : undefined,
      }),
  })

  // ── Derived data ──
  const filtered = useMemo(() => {
    if (!search) return configs ?? []
    const q = search.toLowerCase()
    return (
      configs?.filter(
        (c) =>
          c.modelId.toLowerCase().includes(q) ||
          c.displayName.toLowerCase().includes(q)
      ) ?? []
    )
  }, [configs, search])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const providerById = useMemo(() => {
    const map = new Map<string, Provider>()
    providers?.forEach((p) => map.set(p.id, p))
    return map
  }, [providers])

  // ── Reset filters when page changes ──
  const setProvider = (v: string) => {
    setProviderFilter(v)
    setPage(1)
  }
  const setModality = (v: string) => {
    setModalityFilter(v)
    setPage(1)
  }
  const setCapability = (v: string) => {
    setCapabilityFilter(v)
    setPage(1)
  }
  const setActive = (v: string) => {
    setActiveFilter(v)
    setPage(1)
  }
  const setSearchValue = (v: string) => {
    setSearch(v)
    setPage(1)
  }

  // ── Mutations ──

  const createMutation = useMutation({
    mutationFn: async (data: CreateModelConfigRequest) =>
      adminModelConfigsApi.create(data),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['admin-model-configs'] })
      const previous = queryClient.getQueryData<ModelConfig[]>(['admin-model-configs'])
      return { previous }
    },
    onSuccess: () => {
      setFormError('')
      queryClient.invalidateQueries({ queryKey: ['admin-model-configs'] })
      setDialogOpen(false)
      setFormState(defaultFormState)
      setEditingConfig(null)
      toast('Model created', 'success')
    },
    onError: (error, _, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['admin-model-configs'], context.previous)
      }
      setFormError(getErrorMessage(error))
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-model-configs'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string
      data: UpdateModelConfigRequest
    }) => adminModelConfigsApi.update(id, data),
    onSuccess: () => {
      setFormError('')
      queryClient.invalidateQueries({ queryKey: ['admin-model-configs'] })
      setDialogOpen(false)
      setFormState(defaultFormState)
      setEditingConfig(null)
    },
    onError: (error) => {
      setFormError(getErrorMessage(error))
    },
  })

  const toggleMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: UpdateModelConfigRequest }) =>
      adminModelConfigsApi.update(id, data),
    onMutate: async ({ id, data }) => {
      await queryClient.cancelQueries({ queryKey: ['admin-model-configs'] })
      const previous = queryClient.getQueryData<ModelConfig[]>(['admin-model-configs'])
      queryClient.setQueryData<ModelConfig[]>(['admin-model-configs'], (old) =>
        old?.map((c) => (c.id === id ? { ...c, ...data } as ModelConfig : c))
      )
      return { previous }
    },
    onSuccess: () => {
      setActionError('')
      toast('Model updated', 'success')
    },
    onError: (error, _, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['admin-model-configs'], context.previous)
      }
      const msg = getErrorMessage(error)
      setActionError(msg)
      toast(msg, 'error')
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-model-configs'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => adminModelConfigsApi.remove(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['admin-model-configs'] })
      const previous = queryClient.getQueryData<ModelConfig[]>(['admin-model-configs'])
      queryClient.setQueryData<ModelConfig[]>(['admin-model-configs'], (old) =>
        old?.filter((c) => c.id !== id)
      )
      return { previous }
    },
    onSuccess: (_data, id) => {
      setDeleteError('')
      setDeleteDialogOpen(false)
      setDeleteTarget(null)
      toast(`Model "${id}" deleted`, 'success')
    },
    onError: (error, _id, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['admin-model-configs'], context.previous)
      }
      const msg = getErrorMessage(error)
      setDeleteError(msg)
      toast(`Delete failed: ${msg}`, 'error')
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-model-configs'] })
    },
  })

  // ── Action handlers ──

  const handleSync = async () => {
    if (!syncProvider) return
    setSyncBusy(true)
    setActionError('')
    try {
      await adminModelConfigsApi.sync(syncProvider)
      queryClient.invalidateQueries({ queryKey: ['admin-model-configs'] })
      setSyncProvider('')
    } catch (err) {
      setActionError(getErrorMessage(err))
    } finally {
      setSyncBusy(false)
    }
  }

  const openCreateDialog = () => {
    setIsCreate(true)
    setEditingConfig(null)
    setFormState(defaultFormState)
    setFormError('')
    setDialogOpen(true)
  }

  const openEditDialog = (config: ModelConfig) => {
    setIsCreate(false)
    setEditingConfig(config)
    setFormState(configToFormState(config))
    setFormError('')
    setDialogOpen(true)
  }

  const handleSave = () => {
    // Validate required fields for create mode
    if (isCreate && !formState.providerId.trim()) {
      setFormError('Please select a provider.')
      return
    }
    if (isCreate && !formState.modelId.trim()) {
      setFormError('Model ID is required.')
      return
    }

    setFormBusy(true)

    // Validate JSON fields
    const jsonFields: Record<string, string> = {
      parameterMap: formState.parameterMap,
      extraParams: formState.extraParams,
      capabilities: formState.capabilities,
      constraints: formState.constraints,
      costConfig: formState.costConfig,
    }
    for (const [key, raw] of Object.entries(jsonFields)) {
      if (raw.trim() && !tryParseJson(raw)) {
        setFormError(`Invalid JSON in "${key}" field`)
        setFormBusy(false)
        return
      }
    }

    const parseOrUndef = (raw: string) => {
      const trimmed = raw.trim()
      if (!trimmed) return undefined
      return JSON.parse(trimmed)
    }

    if (isCreate) {
      const payload: CreateModelConfigRequest = {
        providerId: formState.providerId,
        modelId: formState.modelId,
        providerModelId: formState.providerModelId,
        displayName: formState.displayName,
        modality: formState.modality,
        promptFormat: formState.promptFormat,
        endpointType: formState.endpointType,
        parameterMap: parseOrUndef(formState.parameterMap) as Record<string, string> | undefined,
        extraParams: parseOrUndef(formState.extraParams),
        capabilities: parseOrUndef(formState.capabilities) as Record<string, boolean> | undefined,
        constraints: parseOrUndef(formState.constraints),
        costConfig: parseOrUndef(formState.costConfig),
        comfyuiWorkflow: formState.comfyuiWorkflow || undefined,
        isChatEnabled: formState.isChatEnabled,
      }
      createMutation.mutate(payload, { onSettled: () => setFormBusy(false) })
    } else if (editingConfig) {
      const payload: UpdateModelConfigRequest = {
        displayName: formState.displayName,
        modality: formState.modality,
        promptFormat: formState.promptFormat,
        endpointType: formState.endpointType,
        parameterMap: parseOrUndef(formState.parameterMap) as Record<string, string> | undefined,
        extraParams: parseOrUndef(formState.extraParams),
        capabilities: parseOrUndef(formState.capabilities) as Record<string, boolean> | undefined,
        constraints: parseOrUndef(formState.constraints),
        costConfig: parseOrUndef(formState.costConfig),
        comfyuiWorkflow: formState.comfyuiWorkflow || undefined,
        isActive: formState.isActive,
        isChatEnabled: formState.isChatEnabled,
        isDeprecated: formState.isDeprecated,
      }
      updateMutation.mutate(
        { id: editingConfig.id, data: payload },
        { onSettled: () => setFormBusy(false) }
      )
    } else {
      setFormBusy(false)
    }
  }

  const handleDelete = (config: ModelConfig) => {
    setDeleteTarget(config)
    setDeleteError('')
    setDeleteBusy(false)
    setDeleteDialogOpen(true)
  }

  const confirmDelete = () => {
    if (!deleteTarget) return
    setDeleteBusy(true)
    deleteMutation.mutate(deleteTarget.id, {
      onSettled: () => setDeleteBusy(false),
    })
  }

  const handleToggle = (config: ModelConfig, field: 'isActive' | 'isChatEnabled' | 'isDeprecated') => {
    toggleMutation.mutate({
      id: config.id,
      data: { [field]: !config[field] },
    })
  }

  const startInlineEdit = (config: ModelConfig) => {
    setEditingNameId(config.id)
    setEditingNameValue(config.displayName)
    requestAnimationFrame(() => editInputRef.current?.focus())
  }

  const commitInlineEdit = () => {
    if (!editingNameId || !editingNameValue.trim()) {
      setEditingNameId(null)
      return
    }
    toggleMutation.mutate(
      { id: editingNameId, data: { displayName: editingNameValue.trim() } },
      {
        onSuccess: () => {
          toast('Display name updated', 'success')
        },
        onError: (err) => {
          toast(getErrorMessage(err), 'error')
        },
      }
    )
    setEditingNameId(null)
  }

  const cancelInlineEdit = () => {
    setEditingNameId(null)
  }

  const handleInlineKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      commitInlineEdit()
    } else if (e.key === 'Escape') {
      cancelInlineEdit()
    }
  }

  const busy =
    createMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending

  // ── Render ──
  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Model Management</h1>
          <p className="text-sm text-muted-foreground">
            View and manage AI model configurations across providers.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Sync */}
          <Select value={syncProvider} onValueChange={setSyncProvider}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Select provider…" />
            </SelectTrigger>
            <SelectContent>
              {providers?.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            disabled={!syncProvider || syncBusy}
            onClick={handleSync}
          >
            <RefreshCw
              className={`mr-2 h-4 w-4 ${syncBusy ? 'animate-spin' : ''}`}
            />
            Sync
          </Button>
          {/* Add Model */}
          <Button onClick={openCreateDialog}>
            <Plus className="mr-2 h-4 w-4" />
            Add Model
          </Button>
        </div>
      </div>

      {/* ── Action error ── */}
      {actionError && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {actionError}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Select value={providerFilter} onValueChange={setProvider}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="All providers" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All providers</SelectItem>
            {providers?.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={modalityFilter} onValueChange={setModality}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="All modalities" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All modalities</SelectItem>
            {MODALITY_OPTIONS.map((m) => (
              <SelectItem key={m} value={m}>
                {m.charAt(0).toUpperCase() + m.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={capabilityFilter} onValueChange={setCapability}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="All capabilities" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All capabilities</SelectItem>
            {CAPABILITY_OPTIONS.map((c) => (
              <SelectItem key={c} value={c}>
                {c.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={activeFilter} onValueChange={setActive}>
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Active status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All status</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="inactive">Inactive</SelectItem>
          </SelectContent>
        </Select>

        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search models..."
            value={search}
            onChange={(e) => setSearchValue(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Model ID</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead>Provider Model ID</TableHead>
              <TableHead>Display Name</TableHead>
              <TableHead>Modality</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Chat</TableHead>
              <TableHead>Last Synced</TableHead>
              <TableHead className="w-[140px]">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paged.map((config) => {
              const provider = providerById.get(config.providerId)
              return (
                <TableRow
                  key={config.id}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => openEditDialog(config)}
                >
                  <TableCell className="font-mono text-xs">
                    {config.modelId}
                  </TableCell>
                  <TableCell>
                    {provider ? (
                      <div>
                        <div className="font-medium">{provider.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {provider.provider_type}
                        </div>
                      </div>
                    ) : (
                      <span className="text-muted-foreground">Unknown</span>
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {config.providerModelId}
                  </TableCell>
                  <TableCell
                    onClick={(e) => e.stopPropagation()}
                    onDoubleClick={() => startInlineEdit(config)}
                  >
                    {editingNameId === config.id ? (
                      <Input
                        ref={editInputRef}
                        value={editingNameValue}
                        onChange={(e) => setEditingNameValue(e.target.value)}
                        onBlur={commitInlineEdit}
                        onKeyDown={handleInlineKeyDown}
                        className="h-8 text-sm"
                      />
                    ) : (
                      <span className="cursor-text">{config.displayName}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{config.modality}</Badge>
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center gap-1.5">
                      <Badge
                        variant={config.isActive ? 'default' : 'secondary'}
                      >
                        {config.isActive ? 'Active' : 'Inactive'}
                      </Badge>
                      {config.isDeprecated && (
                        <Badge variant="destructive">Deprecated</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Switch
                      checked={config.isChatEnabled}
                      onCheckedChange={() =>
                        handleToggle(config, 'isChatEnabled')
                      }
                      aria-label={
                        config.isChatEnabled
                          ? 'Disable chat for model'
                          : 'Enable chat for model'
                      }
                    />
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {config.lastSyncedAt
                      ? new Date(config.lastSyncedAt).toLocaleString()
                      : 'Never'}
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={config.isActive}
                        onCheckedChange={() =>
                          handleToggle(config, 'isActive')
                        }
                        aria-label={
                          config.isActive
                            ? 'Deactivate model'
                            : 'Activate model'
                        }
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={(e) => {
                          e.stopPropagation()
                          openEditDialog(config)
                        }}
                        aria-label="Edit model"
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-destructive hover:text-destructive"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDelete(config)
                        }}
                        aria-label="Delete model"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>

      {filtered.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-sm text-muted-foreground">
            No model configurations found.
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Configure a provider and sync models to populate this table.
          </p>
        </div>
      )}

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <p className="text-sm text-muted-foreground">Loading models...</p>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Showing {paged.length > 0 ? (page - 1) * PAGE_SIZE + 1 : 0}–
            {Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}{' '}
            models
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {isCreate ? 'Add Model Configuration' : 'Edit Model Configuration'}
            </DialogTitle>
            <DialogDescription>
              {isCreate
                ? 'Create a new AI model configuration.'
                : `Editing: ${editingConfig?.modelId ?? ''}`}
            </DialogDescription>
          </DialogHeader>

            <div className="grid gap-4 py-2">

            {isCreate && (
              <div className="space-y-2">
                <Label>Provider</Label>
                <Select
                  value={formState.providerId}
                  onValueChange={(v) =>
                    setFormState({ ...formState, providerId: v })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select a provider…" />
                  </SelectTrigger>
                  <SelectContent>
                    {providers?.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="modelId">Model ID</Label>
                <Input
                  id="modelId"
                  value={formState.modelId}
                  onChange={(e) =>
                    setFormState({ ...formState, modelId: e.target.value })
                  }
                  disabled={!isCreate}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="providerModelId">Provider Model ID</Label>
                <Input
                  id="providerModelId"
                  value={formState.providerModelId}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      providerModelId: e.target.value,
                    })
                  }
                  disabled={!isCreate}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="displayName">Display Name</Label>
                <Input
                  id="displayName"
                  value={formState.displayName}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      displayName: e.target.value,
                    })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="comfyuiWorkflow">ComfyUI Workflow (JSON)</Label>
                <Input
                  id="comfyuiWorkflow"
                  value={formState.comfyuiWorkflow}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      comfyuiWorkflow: e.target.value,
                    })
                  }
                  placeholder="workflow filename"
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Modality</Label>
                <Select
                  value={formState.modality}
                  onValueChange={(v) =>
                    setFormState({ ...formState, modality: v })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MODALITY_OPTIONS.map((m) => (
                      <SelectItem key={m} value={m}>
                        {m.charAt(0).toUpperCase() + m.slice(1)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Prompt Format</Label>
                <Select
                  value={formState.promptFormat}
                  onValueChange={(v) =>
                    setFormState({ ...formState, promptFormat: v })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PROMPT_FORMATS.map((f) => (
                      <SelectItem key={f} value={f}>
                        {f}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Endpoint Type</Label>
                <Select
                  value={formState.endpointType}
                  onValueChange={(v) =>
                    setFormState({ ...formState, endpointType: v })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ENDPOINT_TYPES.map((e) => (
                      <SelectItem key={e} value={e}>
                        {e.replace(/_/g, ' ')}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex items-center gap-6">
              {!isCreate && (
                <div className="flex items-center gap-2">
                  <Switch
                    id="isActive"
                    checked={formState.isActive}
                    onCheckedChange={(v) =>
                      setFormState({ ...formState, isActive: v })
                    }
                  />
                  <Label htmlFor="isActive">Active</Label>
                </div>
              )}
              <div className="flex items-center gap-2">
                <Switch
                  id="isChatEnabled"
                  checked={formState.isChatEnabled}
                  onCheckedChange={(v) =>
                    setFormState({ ...formState, isChatEnabled: v })
                  }
                />
                <Label htmlFor="isChatEnabled">Chat Enabled</Label>
              </div>
              {!isCreate && (
                <div className="flex items-center gap-2">
                  <Switch
                    id="isDeprecated"
                    checked={formState.isDeprecated}
                    onCheckedChange={(v) =>
                      setFormState({ ...formState, isDeprecated: v })
                    }
                  />
                  <Label htmlFor="isDeprecated">Deprecated</Label>
                </div>
              )}
            </div>

            <JsonField
              label="Parameter Map"
              id="parameterMap"
              value={formState.parameterMap}
              onChange={(v) =>
                setFormState({ ...formState, parameterMap: v })
              }
            />
            <JsonField
              label="Extra Params"
              id="extraParams"
              value={formState.extraParams}
              onChange={(v) =>
                setFormState({ ...formState, extraParams: v })
              }
            />
            <JsonField
              label="Capabilities"
              id="capabilities"
              value={formState.capabilities}
              onChange={(v) =>
                setFormState({ ...formState, capabilities: v })
              }
            />
            <JsonField
              label="Constraints"
              id="constraints"
              value={formState.constraints}
              onChange={(v) =>
                setFormState({ ...formState, constraints: v })
              }
            />
            <JsonField
              label="Cost Config"
              id="costConfig"
              value={formState.costConfig}
              onChange={(v) =>
                setFormState({ ...formState, costConfig: v })
              }
            />

            {formError && (
              <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {formError}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDialogOpen(false)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={busy || formBusy}
            >
              {isCreate
                ? createMutation.isPending
                  ? 'Creating…'
                  : 'Create'
                : updateMutation.isPending
                  ? 'Saving…'
                  : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Model Configuration</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete{' '}
              <span className="font-semibold text-foreground">
                {deleteTarget?.modelId}
              </span>
              ? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>

          {deleteError && (
            <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {deleteError}
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDeleteDialogOpen(false)
                setDeleteTarget(null)
              }}
              disabled={deleteBusy}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDelete}
              disabled={deleteBusy}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              {deleteBusy ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ─── Sub-component: JSON field ────────────────────────────
function JsonField({
  label,
  id,
  value,
  onChange,
}: {
  label: string
  id: string
  value: string
  onChange: (v: string) => void
}) {
  const isValid = !value.trim() || tryParseJson(value) !== null
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label htmlFor={id}>{label}</Label>
        {value.trim() && (
          <Badge variant={isValid ? 'default' : 'destructive'} className="text-[10px]">
            {isValid ? 'Valid JSON' : 'Invalid JSON'}
          </Badge>
        )}
      </div>
      <Textarea
        id={id}
        rows={4}
        className="font-mono text-xs"
        placeholder='{ "key": "value" }'
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}
