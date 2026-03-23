import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, RefreshCw, Layers, RotateCcw } from 'lucide-react'
import { jobsApi } from '../api/client'
import { Button } from '../components/ui/button'
import JobCreateModal from '../components/JobCreateModal'
import { BatchJobModal } from '../components/BatchJobModal'

export default function Jobs() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [showBatch, setShowBatch] = useState(false)
  const [status, setStatus] = useState('')

  const { data: jobs, isLoading } = useQuery({
    queryKey: ['jobs', status],
    queryFn: () => jobsApi.list({ status: status || undefined }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => jobsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const retryMutation = useMutation({
    mutationFn: (id: string) => jobsApi.retry(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    processing: 'bg-blue-100 text-blue-800',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Jobs</h1>
          <p className="text-muted-foreground">Manage your video generation jobs</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowBatch(true)}>
            <Layers className="h-4 w-4 mr-2" />
            Batch Create
          </Button>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4 mr-2" />
            New Job
          </Button>
        </div>
      </div>

      {showCreate && <JobCreateModal onClose={() => setShowCreate(false)} />}
      {showBatch && <BatchJobModal isOpen={showBatch} onClose={() => setShowBatch(false)} />}

      <div className="flex gap-2">
        <Button
          variant={status === '' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setStatus('')}
        >
          All
        </Button>
        {['pending', 'processing', 'completed', 'failed'].map((s) => (
          <Button
            key={s}
            variant={status === s ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatus(s)}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </Button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="border rounded-lg divide-y">
          {jobs?.map((job) => (
            <div
              key={job.id}
              className="p-4 flex items-center justify-between cursor-pointer hover:bg-gray-50"
              onClick={() => navigate(`/jobs/${job.id}`)}
            >
              <div className="flex items-center gap-4">
                {job.thumbnail_path ? (
                  <img
                    src={`/api/uploads/${job.thumbnail_path}`}
                    alt="Job thumbnail"
                    className="w-20 h-14 object-cover rounded"
                  />
                ) : (
                  <div className="w-20 h-14 bg-gray-200 rounded flex items-center justify-center">
                    <RefreshCw className="h-4 w-4 text-gray-400" />
                  </div>
                )}
                <div>
                  <p className="font-medium">{job.id}</p>
                  <p className="text-sm text-muted-foreground">
                    {new Date(job.created_at).toLocaleString()}
                  </p>
                </div>
                <span
                  className={`px-2 py-1 rounded-full text-xs font-medium ${
                    statusColors[job.status]
                  }`}
                >
                  {job.status}
                </span>
                {job.status === 'processing' && (
                  <span className="text-sm text-muted-foreground">
                    {job.progress}%
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                {(job.status === 'failed' || job.status === 'completed') && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation()
                      retryMutation.mutate(job.id)
                    }}
                  >
                    <RotateCcw className="h-4 w-4 mr-1" />
                    Retry
                  </Button>
                )}
                {job.output_path && (
                  <Button variant="outline" size="sm" onClick={(e) => e.stopPropagation()}>
                    Download
                  </Button>
                )}
                {job.preview_path && (
                  <Button variant="outline" size="sm" onClick={(e) => e.stopPropagation()}>
                    Preview
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation()
                    deleteMutation.mutate(job.id)
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
          {(!jobs || jobs.length === 0) && (
            <p className="p-8 text-center text-muted-foreground">No jobs found</p>
          )}
        </div>
      )}
    </div>
  )
}
