export type ErrorSeverity = 'error' | 'critical' | 'warning' | 'info'

export type ErrorOrigin =
  | 'media_generation'
  | 'video_generation'
  | 'audio_generation'
  | 'llm'
  | 'storage'
  | 'upload'
  | 'system'

export interface ErrorEvent {
  id: string
  userId: string | null
  severity: ErrorSeverity
  origin: ErrorOrigin
  message: string
  sourceId: string | null
  sourceType: string | null
  createdAt: string
  readAt: string | null
}

export interface ErrorEventListResponse {
  items: ErrorEvent[]
  total: number
  unreadCount: number
}

export interface ErrorEventFilter {
  severities?: ErrorSeverity[]
  origins?: ErrorOrigin[]
  unreadOnly?: boolean
  limit?: number
  offset?: number
}
