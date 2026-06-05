import { useCallback, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { useNavigate } from 'react-router-dom'
import {
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Trash2,
  AlertTriangle,
  AlertCircle,
  Info,
  Ban,
  Filter,
} from 'lucide-react'
import { useAuthStore } from '../../stores/auth'
import {
  adminApi,
  type AdminErrorEvent,
  type ErrorSeverity,
  type ErrorOrigin,
  type UserDetail,
} from '../../api/client'
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
import { toast } from '../../hooks/use-toast'

const SEVERITY_OPTIONS: { value: ErrorSeverity | 'all'; label: string }[] = [
  { value: 'all', label: 'All Severities' },
  { value: 'critical', label: 'Critical' },
  { value: 'error', label: 'Error' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' },
]

const ORIGIN_OPTIONS: { value: ErrorOrigin | 'all'; label: string }[] = [
  { value: 'all', label: 'All Origins' },
  { value: 'media_generation', label: 'Media Generation' },
  { value: 'video_generation', label: 'Video Generation' },
  { value: 'audio_generation', label: 'Audio Generation' },
  { value: 'llm', label: 'LLM' },
  { value: 'storage', label: 'Storage' },
  { value: 'upload', label: 'Upload' },
  { value: 'system', label: 'System' },
]

const PAGE_SIZE = 50

const severityConfig: Record<ErrorSeverity, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; icon: React.ComponentType<{ className?: string }> }> = {
  critical: { variant: 'destructive', icon: Ban },
  error: { variant: 'destructive', icon: AlertCircle },
  warning: { variant: 'secondary', icon: AlertTriangle },
  info: { variant: 'outline', icon: Info },
}

const getErrorMessage = (error: unknown): string => {
  if (isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail
    if (typeof detail === 'string' && detail) return detail
    if (typeof error.response?.data === 'string' && error.response.data) return error.response.data
    return `Request failed with status ${error.response?.status || 'unknown'}`
  }
  if (error instanceof Error && error.message) return error.message
  return 'An unexpected error occurred.'
}

const formatDateTime = (iso: string): string => {
  const d = new Date(iso)
  return d.toLocaleString()
}

const formatOrigin = (origin: string): string =>
  origin.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

export default function AdminLogs() {
  const navigate = useNavigate()
  const { user: currentUser } = useAuthStore()
  const queryClient = useQueryClient()

  // Admin guard
  if (!currentUser?.is_superuser) {
    navigate('/', { replace: true })
    return null
  }

  // Filter state
  const [severityFilter, setSeverityFilter] = useState<ErrorSeverity | 'all'>('all')
  const [originFilter, setOriginFilter] = useState<ErrorOrigin | 'all'>('all')
  const [userFilter, setUserFilter] = useState<string>('all')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AdminErrorEvent | null>(null)
  const [page, setPage] = useState(0)

  // Build query params
  const queryParams = useMemo(() => {
    const params: {
      severity?: ErrorSeverity[]
      origin?: ErrorOrigin[]
      userId?: string
      limit: number
      offset: number
    } = {
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }
    if (severityFilter !== 'all') params.severity = [severityFilter]
    if (originFilter !== 'all') params.origin = [originFilter]
    if (userFilter !== 'all' && userFilter !== '__system__') params.userId = userFilter
    return params
  }, [severityFilter, originFilter, userFilter, page])

  // Fetch events
  const {
    data: eventsData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['admin-notifications', queryParams],
    queryFn: () => adminApi.getNotifications(queryParams),
    placeholderData: keepPreviousData,
  })

  // Fetch users for filter dropdown and email lookup
  const { data: users } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => adminApi.getUsers(),
  })

  // Build user lookup map
  const userMap = useMemo(() => {
    const map = new Map<string, UserDetail>()
    if (users) {
      for (const u of users) {
        map.set(u.id, u)
      }
    }
    return map
  }, [users])

  const getUserEmail = useCallback(
    (userId: string | null): string => {
      if (!userId) return 'System'
      return userMap.get(userId)?.email ?? 'Unknown User'
    },
    [userMap],
  )

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (eventId: string) => adminApi.deleteNotification(eventId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-notifications'] })
      toast('Event deleted successfully', 'success')
      setDeleteTarget(null)
    },
    onError: (err: unknown) => {
      toast(getErrorMessage(err), 'error')
    },
  })

  // Fetch details for expanded row
  const { data: expandedDetails } = useQuery({
    queryKey: ['admin-notification-detail', expandedId],
    queryFn: () => adminApi.getNotification(expandedId!),
    enabled: !!expandedId,
  })

  const events = eventsData?.items ?? []
  const total = eventsData?.total ?? 0
  const totalPages = Math.ceil(total / PAGE_SIZE)

  const resetFilters = () => {
    setSeverityFilter('all')
    setOriginFilter('all')
    setUserFilter('all')
    setPage(0)
  }

  const hasActiveFilters = severityFilter !== 'all' || originFilter !== 'all' || userFilter !== 'all'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Error Logs</h1>
          <p className="text-muted-foreground">
            System and user error events ({total} total)
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border p-4">
        <Filter className="h-4 w-4 text-muted-foreground" />

        <Select
          value={severityFilter}
          onValueChange={(v) => {
            setSeverityFilter(v as ErrorSeverity | 'all')
            setPage(0)
          }}
        >
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Severity" />
          </SelectTrigger>
          <SelectContent>
            {SEVERITY_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={originFilter}
          onValueChange={(v) => {
            setOriginFilter(v as ErrorOrigin | 'all')
            setPage(0)
          }}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Origin" />
          </SelectTrigger>
          <SelectContent>
            {ORIGIN_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={userFilter}
          onValueChange={(v) => {
            setUserFilter(v)
            setPage(0)
          }}
        >
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="User" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Users</SelectItem>

            {users?.map((u) => (
              <SelectItem key={u.id} value={u.id}>
                {u.email}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {hasActiveFilters && (
          <Button variant="ghost" size="sm" onClick={resetFilters}>
            Clear Filters
          </Button>
        )}
      </div>

      {/* Error state */}
      {isError && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-destructive">
          <p className="font-medium">Failed to load error events</p>
          <p className="text-sm">{getErrorMessage(error)}</p>
        </div>
      )}

      {/* Table */}
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[40px]" />
              <TableHead className="w-[100px]">Severity</TableHead>
              <TableHead className="w-[140px]">Origin</TableHead>
              <TableHead>Message</TableHead>
              <TableHead className="w-[180px]">User</TableHead>
              <TableHead className="w-[170px]">Timestamp</TableHead>
              <TableHead className="w-[60px]" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                  Loading events...
                </TableCell>
              </TableRow>
            )}

            {!isLoading && events.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                  No error events found.
                </TableCell>
              </TableRow>
            )}

            {events.map((event) => {
              const isExpanded = expandedId === event.id
              const config = severityConfig[event.severity]
              const SeverityIcon = config.icon

              return (
                <EventRow
                  key={event.id}
                  event={event}
                  isExpanded={isExpanded}
                  details={isExpanded ? expandedDetails : undefined}
                  severityIcon={SeverityIcon}
                  severityVariant={config.variant}
                  userEmail={getUserEmail(event.userId)}
                  onToggleExpand={() => setExpandedId(isExpanded ? null : event.id)}
                  onDelete={() => setDeleteTarget(event)}
                />
              )
            })}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {page + 1} of {totalPages} ({total} events)
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      {/* Delete confirmation dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Error Event</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this error event? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          {deleteTarget && (
            <div className="rounded-md bg-muted p-3 text-sm">
              <p className="font-medium">{deleteTarget.message}</p>
              <p className="text-muted-foreground mt-1">
                {formatOrigin(deleteTarget.origin)} &middot; {deleteTarget.severity} &middot;{' '}
                {formatDateTime(deleteTarget.createdAt)}
              </p>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ─── Event Row Component ──────────────────────────────────────

interface EventRowProps {
  event: AdminErrorEvent
  isExpanded: boolean
  details: AdminErrorEvent | undefined
  severityIcon: React.ComponentType<{ className?: string }>
  severityVariant: 'default' | 'secondary' | 'destructive' | 'outline'
  userEmail: string
  onToggleExpand: () => void
  onDelete: () => void
}

function EventRow({
  event,
  isExpanded,
  details,
  severityIcon: SeverityIcon,
  severityVariant,
  userEmail,
  onToggleExpand,
  onDelete,
}: EventRowProps) {
  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-muted/50"
        onClick={onToggleExpand}
      >
        <TableCell>
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </TableCell>
        <TableCell>
          <Badge variant={severityVariant} className="gap-1">
            <SeverityIcon className="h-3 w-3" />
            {event.severity}
          </Badge>
        </TableCell>
        <TableCell className="text-sm text-muted-foreground">
          {formatOrigin(event.origin)}
        </TableCell>
        <TableCell className="max-w-[400px] truncate text-sm font-medium">
          {event.message}
        </TableCell>
        <TableCell className="text-sm">
          {event.userId === null ? (
            <Badge variant="outline" className="text-xs">
              System
            </Badge>
          ) : (
            <span className="text-sm">{userEmail}</span>
          )}
        </TableCell>
        <TableCell className="text-sm text-muted-foreground">
          {formatDateTime(event.createdAt)}
        </TableCell>
        <TableCell>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-destructive hover:text-destructive"
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </TableCell>
      </TableRow>

      {/* Expanded details panel */}
      {isExpanded && (
        <TableRow>
          <TableCell colSpan={7} className="bg-muted/30 p-0">
            <div className="p-4 space-y-3">
              {/* Metadata row */}
              <div className="flex flex-wrap gap-4 text-sm">
                {event.sourceType && (
                  <div>
                    <span className="text-muted-foreground">Source: </span>
                    <span className="font-mono">{event.sourceType}</span>
                  </div>
                )}
                {event.sourceId && (
                  <div>
                    <span className="text-muted-foreground">Source ID: </span>
                    <span className="font-mono text-xs">{event.sourceId}</span>
                  </div>
                )}
                {event.readAt && (
                  <div>
                    <span className="text-muted-foreground">Read at: </span>
                    <span>{formatDateTime(event.readAt)}</span>
                  </div>
                )}
                {!event.readAt && (
                  <div>
                    <Badge variant="outline" className="text-xs">
                      Unread
                    </Badge>
                  </div>
                )}
              </div>

              {/* Details / Stack trace */}
              {details?.details ? (
                <div className="space-y-2">
                  <h4 className="text-sm font-medium">Details</h4>
                  <pre className="max-h-[400px] overflow-auto rounded-md bg-zinc-950 p-4 text-xs text-zinc-100 font-mono whitespace-pre-wrap break-all">
                    {JSON.stringify(details.details, null, 2)}
                  </pre>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground italic">
                  {details ? 'No additional details available.' : 'Loading details...'}
                </p>
              )}
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  )
}
