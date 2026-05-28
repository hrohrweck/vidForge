import api from './client'

export interface ModelConfig {
  id: string
  providerId: string
  modelId: string
  providerModelId: string
  displayName: string
  modality: 'text' | 'image' | 'video'
  promptFormat: 'string' | 'array'
  endpointType: string
  parameterMap?: Record<string, string>
  extraParams?: Record<string, unknown>
  capabilities?: Record<string, boolean>
  constraints?: Record<string, unknown>
  costConfig?: Record<string, unknown>
  comfyuiWorkflow?: string
  isActive: boolean
  isDeprecated: boolean
  lastSyncedAt?: string
  createdAt: string
  updatedAt: string
}

export interface CreateModelConfigRequest {
  providerId: string
  modelId: string
  providerModelId: string
  displayName: string
  modality: string
  promptFormat?: string
  endpointType: string
  parameterMap?: Record<string, string>
  extraParams?: Record<string, unknown>
  capabilities?: Record<string, boolean>
  constraints?: Record<string, unknown>
  costConfig?: Record<string, unknown>
  comfyuiWorkflow?: string
}

export interface UpdateModelConfigRequest {
  displayName?: string
  modality?: string
  promptFormat?: string
  endpointType?: string
  parameterMap?: Record<string, string>
  extraParams?: Record<string, unknown>
  capabilities?: Record<string, boolean>
  constraints?: Record<string, unknown>
  costConfig?: Record<string, unknown>
  comfyuiWorkflow?: string
  isActive?: boolean
  isDeprecated?: boolean
}

export interface ListModelConfigsParams {
  providerId?: string
  modality?: string
  isActive?: boolean
}

export interface SyncResult {
  status: string
  provider?: string
}

export const adminModelConfigsApi = {
  list: async (params?: ListModelConfigsParams): Promise<ModelConfig[]> => {
    const queryParams: Record<string, string> = {}
    if (params?.providerId) queryParams.provider_id = params.providerId
    if (params?.modality) queryParams.modality = params.modality
    if (params?.isActive !== undefined) queryParams.is_active = String(params.isActive)

    const response = await api.get<ModelConfig[]>('/admin/model-configs', {
      params: queryParams,
    })
    return response.data
  },

  get: async (id: string): Promise<ModelConfig> => {
    const response = await api.get<ModelConfig>(`/admin/model-configs/${id}`)
    return response.data
  },

  create: async (data: CreateModelConfigRequest): Promise<ModelConfig> => {
    // Map camelCase frontend keys → snake_case backend keys
    const payload = {
      provider_id: data.providerId,
      model_id: data.modelId,
      provider_model_id: data.providerModelId,
      display_name: data.displayName,
      modality: data.modality,
      prompt_format: data.promptFormat,
      endpoint_type: data.endpointType,
      parameter_map: data.parameterMap,
      extra_params: data.extraParams,
      capabilities: data.capabilities,
      constraints: data.constraints,
      cost_config: data.costConfig,
      comfyui_workflow: data.comfyuiWorkflow,
    }
    const response = await api.post<ModelConfig>('/admin/model-configs', payload)
    return response.data
  },

  update: async (id: string, data: UpdateModelConfigRequest): Promise<ModelConfig> => {
    // Map camelCase frontend keys → snake_case backend keys
    const payload: Record<string, unknown> = {}
    if (data.displayName !== undefined) payload.display_name = data.displayName
    if (data.modality !== undefined) payload.modality = data.modality
    if (data.promptFormat !== undefined) payload.prompt_format = data.promptFormat
    if (data.endpointType !== undefined) payload.endpoint_type = data.endpointType
    if (data.parameterMap !== undefined) payload.parameter_map = data.parameterMap
    if (data.extraParams !== undefined) payload.extra_params = data.extraParams
    if (data.capabilities !== undefined) payload.capabilities = data.capabilities
    if (data.constraints !== undefined) payload.constraints = data.constraints
    if (data.costConfig !== undefined) payload.cost_config = data.costConfig
    if (data.comfyuiWorkflow !== undefined) payload.comfyui_workflow = data.comfyuiWorkflow
    if (data.isActive !== undefined) payload.is_active = data.isActive
    if (data.isDeprecated !== undefined) payload.is_deprecated = data.isDeprecated

    const response = await api.put<ModelConfig>(`/admin/model-configs/${id}`, payload)
    return response.data
  },

  remove: async (id: string): Promise<void> => {
    await api.delete(`/admin/model-configs/${id}`)
  },

  sync: async (providerId: string): Promise<SyncResult> => {
    const response = await api.post<SyncResult>(`/admin/model-configs/${providerId}/sync`)
    return response.data
  },
}
