import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { jobsApi, templatesApi, Template } from '../api/client'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'

interface BatchJobModalProps {
  isOpen: boolean
  onClose: () => void
}

export function BatchJobModal({ isOpen, onClose }: BatchJobModalProps) {
  const [mode, setMode] = useState<'manual' | 'csv'>('manual')
  const [selectedTemplate, setSelectedTemplate] = useState<string>('')
  const [jobInputs, setJobInputs] = useState<string>('')
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [autoStart, setAutoStart] = useState(true)
  const [providerPreference, setProviderPreference] = useState<'auto' | 'local' | 'runpod'>('auto')
  
  const queryClient = useQueryClient()
  
  const { data: templates } = useQuery({
    queryKey: ['templates'],
    queryFn: async () => {
      const res = await templatesApi.list()
      return res.data
    },
  })
  
  const createBatchMutation = useMutation({
    mutationFn: async (data: {
      template_id: string
      jobs: Record<string, unknown>[]
      auto_start: boolean
      provider_preference: 'auto' | 'local' | 'runpod'
    }) => {
      return jobsApi.createBatch(data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      onClose()
    },
  })
  
  const createCsvMutation = useMutation({
    mutationFn: async () => {
      if (!csvFile || !selectedTemplate) return
      return jobsApi.createFromCsv(
        selectedTemplate,
        csvFile,
        autoStart,
        providerPreference
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      onClose()
    },
  })
  
  const handleSubmit = () => {
    if (!selectedTemplate) return
    
    if (mode === 'manual') {
      try {
        const jobs = JSON.parse(jobInputs)
        if (!Array.isArray(jobs)) {
          alert('Input must be a JSON array')
          return
        }
        createBatchMutation.mutate({
          template_id: selectedTemplate,
          jobs,
          auto_start: autoStart,
          provider_preference: providerPreference,
        })
      } catch {
        alert('Invalid JSON format')
      }
    } else {
      if (!csvFile) {
        alert('Please select a CSV file')
        return
      }
      createCsvMutation.mutate()
    }
  }
  
  if (!isOpen) return null
  
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto border shadow-xl">
        <h2 className="text-xl font-semibold mb-4">Create Batch Jobs</h2>
        
        <div className="space-y-4">
          <div>
            <Label>Mode</Label>
            <div className="flex gap-2 mt-1">
              <Button
                variant={mode === 'manual' ? 'default' : 'outline'}
                onClick={() => setMode('manual')}
              >
                Manual Input
              </Button>
              <Button
                variant={mode === 'csv' ? 'default' : 'outline'}
                onClick={() => setMode('csv')}
              >
                Upload CSV
              </Button>
            </div>
          </div>
          
          <div>
            <Label htmlFor="template">Template</Label>
            <select
              id="template"
              className="w-full mt-1 border rounded px-3 py-2"
              value={selectedTemplate}
              onChange={(e) => setSelectedTemplate(e.target.value)}
            >
              <option value="">Select a template...</option>
              {templates?.map((t: Template) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <Label htmlFor="batch-provider">Provider Preference</Label>
            <select
              id="batch-provider"
              className="w-full mt-1 border rounded px-3 py-2"
              value={providerPreference}
              onChange={(e) =>
                setProviderPreference(e.target.value as 'auto' | 'local' | 'runpod')
              }
            >
              <option value="auto">Auto</option>
              <option value="local">Local</option>
              <option value="runpod">RunPod</option>
            </select>
          </div>
          
          {mode === 'manual' && (
            <div>
              <Label htmlFor="jobInputs">Job Inputs (JSON Array)</Label>
              <textarea
                id="jobInputs"
                className="w-full mt-1 border rounded px-3 py-2 font-mono text-sm"
                rows={10}
                placeholder='[{"prompt": "First video"}, {"prompt": "Second video"}]'
                value={jobInputs}
                onChange={(e) => setJobInputs(e.target.value)}
              />
              <p className="text-sm text-gray-500 mt-1">
                Enter a JSON array where each object contains the input data for one job
              </p>
            </div>
          )}
          
          {mode === 'csv' && (
            <div>
              <Label htmlFor="csvFile">CSV File</Label>
              <Input
                id="csvFile"
                type="file"
                accept=".csv"
                className="mt-1"
                onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
              />
              <p className="text-sm text-gray-500 mt-1">
                CSV file with headers matching template input names. Each row creates one job.
              </p>
            </div>
          )}
          
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="autoStart"
              checked={autoStart}
              onChange={(e) => setAutoStart(e.target.checked)}
              className="rounded"
            />
            <Label htmlFor="autoStart">Start jobs automatically</Label>
          </div>
        </div>
        
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!selectedTemplate || (mode === 'csv' && !csvFile)}
          >
            Create Jobs
          </Button>
        </div>
        
        {(createBatchMutation.isError || createCsvMutation.isError) && (
          <p className="text-red-500 mt-2">
            Error creating jobs. Please check your input.
          </p>
        )}
      </div>
    </div>
  )
}
