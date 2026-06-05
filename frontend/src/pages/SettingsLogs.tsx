import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react'
import { notificationsApi } from '../api/client'
import type { ErrorSeverity, ErrorOrigin, ErrorEvent } from '../api/types/notifications'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Switch } from '../components/ui/switch'
import { Label } from '../components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu'

const SEVERITIES: ErrorSeverity[] = ['error', 'critical', 'warning', 'info']
const ORIGINS: ErrorOrigin[] = [
  'media_generation',
  'video_generation',
  'audio_generation',
  'llm',
  'storage',
  'upload',
  'system',
]

const PAGE_SIZE = 50

const severityVariants: Record<ErrorSeverity, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  critical: 'destructive',
  error: 'destructive',
  warning: 'secondary',
  info: 'outline',
}

export default function SettingsLogs() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(0)
  const [severities, setSeverities] = useState<ErrorSeverity[]>([])
  const [origins, setOrigins] = useState<ErrorOrigin[]>([])
  const [unreadOnly, setUnreadOnly] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['notifications', page, severities, origins, unreadOnly],
    queryFn: () =>
      notificationsApi.list({
        severities: severities.length > 0 ? severities : undefined,
        origins: origins.length > 0 ? origins : undefined,
        unreadOnly: unreadOnly || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  })

  const markAsReadMutation = useMutation({
    mutationFn: (id: string) => notificationsApi.markAsRead(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const markAllReadMutation = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const toggleSeverity = (severity: ErrorSeverity) => {
    setSeverities((prev) =>
      prev.includes(severity) ? prev.filter((s) => s !== severity) : [...prev, severity]
    )
    setPage(0)
  }

  const toggleOrigin = (origin: ErrorOrigin) => {
    setOrigins((prev) =>
      prev.includes(origin) ? prev.filter((o) => o !== origin) : [...prev, origin]
    )
    setPage(0)
  }

  const handleRowClick = (event: ErrorEvent) => {
    if (!event.readAt) {
      markAsReadMutation.mutate(event.id)
    }
  }

  const handleMarkAllRead = () => {
    markAllReadMutation.mutate()
  }

  const totalPages = Math.ceil((data?.total || 0) / PAGE_SIZE)
  const hasPrev = page > 0
  const hasNext = page < totalPages - 1

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Error Logs</h2>
          <p className="text-muted-foreground">View and manage error events</p>
        </div>
        <Button
          variant="outline"
          onClick={handleMarkAllRead}
          disabled={!data?.unreadCount || markAllReadMutation.isPending}
        >
          <Check className="h-4 w-4 mr-2" />
          Mark All as Read
        </Button>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap gap-4 items-center">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              Severity {severities.length > 0 && `(${severities.length})`}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            {SEVERITIES.map((severity) => (
              <DropdownMenuCheckboxItem
                key={severity}
                checked={severities.includes(severity)}
                onCheckedChange={() => toggleSeverity(severity)}
                className="capitalize"
              >
                {severity}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              Origin {origins.length > 0 && `(${origins.length})`}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            {ORIGINS.map((origin) => (
              <DropdownMenuCheckboxItem
                key={origin}
                checked={origins.includes(origin)}
                onCheckedChange={() => toggleOrigin(origin)}
                className="capitalize"
              >
                {origin.replace('_', ' ')}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <div className="flex items-center gap-2">
          <Switch
            id="unread-only"
            checked={unreadOnly}
            onCheckedChange={(checked) => {
              setUnreadOnly(checked)
              setPage(0)
            }}
          />
          <Label htmlFor="unread-only" className="text-sm font-medium">
            Unread only
          </Label>
        </div>
      </div>

      {/* Table */}
      <div className="border rounded-lg bg-card text-card-foreground shadow-sm overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date/Time</TableHead>
              <TableHead>Severity</TableHead>
              <TableHead>Origin</TableHead>
              <TableHead>Message</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center py-8 text-muted-foreground">
                  <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
                  Loading logs...
                </TableCell>
              </TableRow>
            ) : !data?.items.length ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center py-8 text-muted-foreground">
                  No errors logged
                </TableCell>
              </TableRow>
            ) : (
              data.items.map((event) => (
                <TableRow
                  key={event.id}
                  className={`cursor-pointer transition-colors hover:bg-muted/50 ${
                    !event.readAt ? 'bg-accent/30' : ''
                  }`}
                  onClick={() => handleRowClick(event)}
                >
                  <TableCell className="text-muted-foreground whitespace-nowrap">
                    {new Date(event.createdAt).toLocaleString()}
                  </TableCell>
                  <TableCell>
                    <Badge variant={severityVariants[event.severity]} className="capitalize">
                      {event.severity}
                    </Badge>
                  </TableCell>
                  <TableCell className="capitalize">
                    {event.origin.replace('_', ' ')}
                  </TableCell>
                  <TableCell className="max-w-md truncate">{event.message}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-muted-foreground">
            Page {page + 1} of {totalPages} ({data?.total || 0} total)
            {data?.unreadCount ? ` • ${data.unreadCount} unread` : ''}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => p - 1)}
              disabled={!hasPrev}
            >
              <ChevronLeft className="h-4 w-4 mr-1" />
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => p + 1)}
              disabled={!hasNext}
            >
              Next
              <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
