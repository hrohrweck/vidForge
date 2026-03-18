import { useQuery } from '@tanstack/react-query'
import { Plus, Video, Clock, CheckCircle, XCircle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { jobsApi, templatesApi } from '../api/client'
import { Button } from '../components/ui/button'

export default function Dashboard() {
  const { data: jobs } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => jobsApi.list({ limit: 5 }),
  })

  const { data: templates } = useQuery({
    queryKey: ['templates'],
    queryFn: () => templatesApi.list(),
  })

  const statusColors: Record<string, string> = {
    pending: 'text-yellow-600',
    processing: 'text-blue-600',
    completed: 'text-green-600',
    failed: 'text-red-600',
  }

  const statusIcons: Record<string, typeof Clock> = {
    pending: Clock,
    processing: Clock,
    completed: CheckCircle,
    failed: XCircle,
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground">
            Welcome to VidForge - AI-powered video generation
          </p>
        </div>
        <Link to="/jobs">
          <Button>
            <Plus className="h-4 w-4 mr-2" />
            New Job
          </Button>
        </Link>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <div className="p-6 border rounded-lg">
          <div className="flex items-center gap-2">
            <Video className="h-5 w-5 text-muted-foreground" />
            <span className="text-sm font-medium">Total Jobs</span>
          </div>
          <p className="text-3xl font-bold mt-2">{jobs?.length || 0}</p>
        </div>
        <div className="p-6 border rounded-lg">
          <div className="flex items-center gap-2">
            <CheckCircle className="h-5 w-5 text-green-600" />
            <span className="text-sm font-medium">Completed</span>
          </div>
          <p className="text-3xl font-bold mt-2">
            {jobs?.filter((j) => j.status === 'completed').length || 0}
          </p>
        </div>
        <div className="p-6 border rounded-lg">
          <div className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-blue-600" />
            <span className="text-sm font-medium">Processing</span>
          </div>
          <p className="text-3xl font-bold mt-2">
            {jobs?.filter((j) => j.status === 'processing').length || 0}
          </p>
        </div>
        <div className="p-6 border rounded-lg">
          <div className="flex items-center gap-2">
            <XCircle className="h-5 w-5 text-red-600" />
            <span className="text-sm font-medium">Failed</span>
          </div>
          <p className="text-3xl font-bold mt-2">
            {jobs?.filter((j) => j.status === 'failed').length || 0}
          </p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="text-xl font-semibold mb-4">Recent Jobs</h2>
          <div className="border rounded-lg divide-y">
            {jobs?.slice(0, 5).map((job) => {
              const StatusIcon = statusIcons[job.status] || Clock
              return (
                <div key={job.id} className="p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <StatusIcon
                      className={`h-5 w-5 ${statusColors[job.status]}`}
                    />
                    <div>
                      <p className="font-medium">{job.id.slice(0, 8)}...</p>
                      <p className="text-sm text-muted-foreground">
                        {new Date(job.created_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                  <span
                    className={`text-sm capitalize ${statusColors[job.status]}`}
                  >
                    {job.status}
                  </span>
                </div>
              )
            })}
            {(!jobs || jobs.length === 0) && (
              <p className="p-4 text-muted-foreground text-center">No jobs yet</p>
            )}
          </div>
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-4">Templates</h2>
          <div className="border rounded-lg divide-y">
            {templates?.slice(0, 5).map((template) => (
              <div key={template.id} className="p-4">
                <p className="font-medium">{template.name}</p>
                <p className="text-sm text-muted-foreground">
                  {template.description}
                </p>
              </div>
            ))}
            {(!templates || templates.length === 0) && (
              <p className="p-4 text-muted-foreground text-center">
                No templates available
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
