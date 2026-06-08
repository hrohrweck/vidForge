import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, RefreshCw, Layers, RotateCcw } from 'lucide-react'
import { jobsApi } from '../api/client'
import { Button } from '../components/ui/button'
import JobCreateModal from '../components/JobCreateModal'
import { BatchJobModal } from '../components/BatchJobModal'
import { Badge } from '../components/ui/badge'

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

  const statusVariants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
    pending: 'secondary',
    processing: 'default',
    completed: 'outline',
    failed: 'destructive',
  }

  const formatCost = (cost: number | null | undefined) => {
    return cost == null ? '-' : `$${cost.toFixed(4)}`
  }

  return (
    <div className="h-full flex flex-col w-full px-2.5">
      <div className="shrink-0 pt-4 pb-2">
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
      </div>

      <div className="shrink-0 pb-2">
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
              className="capitalize"
            >
              {s}
            </Button>
          ))}
        </div>
      </div>

      {showCreate && <JobCreateModal onClose={() => setShowCreate(false)} />}
      {showBatch && <BatchJobModal isOpen={showBatch} onClose={() => setShowBatch(false)} />}

      <div className="flex-1 overflow-auto border rounded-lg bg-card text-card-foreground shadow-sm">
        <table className="w-full text-sm text-left">
          <thead className="bg-muted/50 text-muted-foreground sticky top-0 z-10">
            <tr>
              <th className="px-6 py-3 font-medium">Title</th>
              <th className="px-6 py-3 font-medium">Status</th>
              <th className="px-6 py-3 font-medium">Cost</th>
              <th className="px-6 py-3 font-medium">Created</th>
              <th className="px-6 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {isLoading ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                  <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
                  Loading jobs...
                </td>
              </tr>
            ) : jobs?.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                  No jobs found
                </td>
              </tr>
            ) : (
              jobs?.map((job) => (
                <tr
                  key={job.id}
                  className="hover:bg-muted/50 transition-colors cursor-pointer"
                  onClick={() => navigate(`/jobs/${job.id}`)}
                >
                  <td className="px-6 py-4 font-medium">
                    {job.title || job.id.slice(0, 8)}
                  </td>
                  <td className="px-6 py-4">
                    <Badge variant={statusVariants[job.status] || 'default'}>
                      {job.status}
                    </Badge>
                  </td>
                  <td className="px-6 py-4 font-mono text-xs">
                    {formatCost(job.cost)}
                  </td>
                  <td className="px-6 py-4 text-muted-foreground">
                    {new Date(job.created_at).toLocaleString()}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={(e) => { e.stopPropagation(); navigate(`/jobs/${job.id}`) }}
                      >
                        View
                      </Button>
                      <Button
                        variant="default"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation()
                          navigate(`/editor/${job.id}`)
                        }}
                      >
                        Edit
                      </Button>
                      {job.status === 'failed' && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={(e) => { e.stopPropagation(); retryMutation.mutate(job.id) }}
                          disabled={retryMutation.isPending}
                        >
                          <RotateCcw className="h-4 w-4" />
                        </Button>
                      )}
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation()
                          if (window.confirm('Are you sure you want to delete this job?')) {
                            deleteMutation.mutate(job.id)
                          }
                        }}
                        disabled={deleteMutation.isPending}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
