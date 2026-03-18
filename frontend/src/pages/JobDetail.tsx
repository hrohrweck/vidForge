import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Trash2, Download, Play, RefreshCw } from 'lucide-react'
import { jobsApi, type Job } from '../api/client'
import { Button } from '../components/ui/button'
import VideoPlayer from '../components/VideoPlayer'
import { useAuthStore } from '../stores/auth'

interface WebSocketMessage {
  type: 'progress' | 'completed' | 'error' | 'failed'
  job_id: string
  progress?: number
  status?: string
  error?: string
  output_path?: string
  preview_path?: string
}

export default function JobDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [localJob, setLocalJob] = useState<Job | null>(null)
  const token = useAuthStore((state) => state.token)

  const { data: serverJob, isLoading } = useQuery({
    queryKey: ['job', id],
    queryFn: () => jobsApi.get(id!),
    enabled: !!id,
  })

  const job = localJob || serverJob?.data

  const deleteMutation = useMutation({
    mutationFn: () => jobsApi.delete(id!),
    onSuccess: () => {
      navigate('/jobs')
    },
  })

  const startMutation = useMutation({
    mutationFn: () => fetch(`/api/jobs/${id}/start`, { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['job', id] })
    },
  })

  useEffect(() => {
    if (!id || !job || job.status === 'completed' || job.status === 'failed') return

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/jobs/${id}`

    const ws = new WebSocket(wsUrl)

    ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data)
        if (message.job_id === id) {
          setLocalJob((prev) => {
            if (!prev) return null
            return {
              ...prev,
              status: message.status || prev.status,
              progress: message.progress ?? prev.progress,
              error_message: message.error || null,
              output_path: message.output_path || prev.output_path,
              preview_path: message.preview_path || prev.preview_path,
            }
          })

          if (message.type === 'completed' || message.type === 'failed') {
            queryClient.invalidateQueries({ queryKey: ['job', id] })
            queryClient.invalidateQueries({ queryKey: ['jobs'] })
          }
        }
      } catch {
        console.error('Failed to parse WebSocket message')
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    return () => {
      ws.close()
    }
  }, [id, job?.status, queryClient])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!job) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Job not found</p>
        <Button className="mt-4" onClick={() => navigate('/jobs')}>
          Back to Jobs
        </Button>
      </div>
    )
  }

  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    processing: 'bg-blue-100 text-blue-800',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/jobs')}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back
        </Button>
      </div>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Job {job.id.slice(0, 8)}...</h1>
          <p className="text-muted-foreground">
            Created {new Date(job.created_at).toLocaleString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`px-3 py-1 rounded-full text-sm font-medium ${
              statusColors[job.status]
            }`}
          >
            {job.status}
          </span>
          {job.status === 'pending' && (
            <Button onClick={() => startMutation.mutate()}>
              <Play className="h-4 w-4 mr-2" />
              Start
            </Button>
          )}
          <Button variant="destructive" onClick={() => deleteMutation.mutate()}>
            <Trash2 className="h-4 w-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      {job.status === 'processing' && (
        <div className="border rounded-lg p-6 space-y-4">
          <h2 className="text-lg font-semibold">Progress</h2>
          <div className="w-full bg-gray-200 rounded-full h-4">
            <div
              className="bg-blue-600 h-4 rounded-full transition-all duration-300"
              style={{ width: `${job.progress}%` }}
            />
          </div>
          <p className="text-sm text-muted-foreground text-center">
            {job.progress}% complete
          </p>
        </div>
      )}

      {job.error_message && (
        <div className="border border-red-200 bg-red-50 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-red-800">Error</h2>
          <p className="text-red-700 mt-2">{job.error_message}</p>
        </div>
      )}

      {(job.output_path || job.preview_path) && (
        <div className="border rounded-lg p-6 space-y-4">
          <h2 className="text-lg font-semibold">Output</h2>
          <div className="aspect-video bg-black rounded-lg overflow-hidden">
            <VideoPlayer
              src={`/api/uploads/stream/${job.output_path}`}
              previewSrc={job.preview_path ? `/api/uploads/stream/${job.preview_path}` : undefined}
              showControls={true}
              showDownload={true}
              className="w-full h-full"
            />
          </div>
          <div className="flex gap-4">
            {job.preview_path && (
              <a
                href={`/api/uploads/download/${job.preview_path}`}
                download
              >
                <Button variant="outline">
                  <Download className="h-4 w-4 mr-2" />
                  Download Preview
                </Button>
              </a>
            )}
            {job.output_path && (
              <a
                href={`/api/uploads/download/${job.output_path}`}
                download
              >
                <Button>
                  <Download className="h-4 w-4 mr-2" />
                  Download Video
                </Button>
              </a>
            )}
          </div>
        </div>
      )}

      <div className="border rounded-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold">Details</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground">Status</p>
            <p className="font-medium">{job.status}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Progress</p>
            <p className="font-medium">{job.progress}%</p>
          </div>
          <div>
            <p className="text-muted-foreground">Started</p>
            <p className="font-medium">
              {job.started_at ? new Date(job.started_at).toLocaleString() : '-'}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">Completed</p>
            <p className="font-medium">
              {job.completed_at
                ? new Date(job.completed_at).toLocaleString()
                : '-'}
            </p>
          </div>
        </div>
        {job.input_data && Object.keys(job.input_data).length > 0 && (
          <div className="mt-4">
            <p className="text-muted-foreground mb-2">Input Data</p>
            <pre className="bg-gray-100 p-4 rounded text-xs overflow-auto">
              {JSON.stringify(job.input_data, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
