import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Eye, FileText, Loader2 } from 'lucide-react'
import { templatesApi, type Template } from '../api/client'
import { Button } from '../components/ui/button'
import JobCreateModal from '../components/JobCreateModal'

interface TemplateDetailModalProps {
  template: Template
  onClose: () => void
  onUse: () => void
}

function TemplateDetailModal({ template, onClose, onUse }: TemplateDetailModalProps) {
  const config = template.config as {
    inputs?: Array<{
      name: string
      type: string
      required?: boolean
      description?: string
      default?: unknown
      options?: string[]
    }>
    pipeline?: Array<{
      step: string
      description?: string
      model?: string
    }>
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto border">
        <div className="p-6 border-b">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-xl font-semibold">{template.name}</h2>
              {template.is_builtin && (
                <span className="text-xs bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 px-2 py-0.5 rounded mt-2 inline-block">
                  Built-in
                </span>
              )}
            </div>
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
              ×
            </button>
          </div>
        </div>

 <div>
  )
</footer>
</div>
</div>
</div>
</div>
</div>
</>
                    <div className="flex justify-end gap-3 p-6 border-t">
                      <Button variant="outline" onClick={onClose}>
                        Cancel
                      </Button>
                      <Button onClick={onClose}>Close</Button>
                    </div>
                  </div>
                </div>
              )
            </div>
        </div>

export default function Templates() {
  const queryClient = useQueryClient()
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)

  const { data: templates, isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => templatesApi.list(),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => templatesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['templates'] })
    },
  })

  const handleUseTemplate = (_template: Template) => {
    setShowCreateModal(true)
    setSelectedTemplate(null)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Templates</h1>
          <p className="text-muted-foreground">
            Video generation templates for different use cases
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {templates?.data?.map((template) => {
            const config = template.config as { inputs?: unknown[] }
            return (
              <div
                key={template.id}
                className="border rounded-lg p-6 hover:shadow-md transition"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <FileText className="h-5 w-5 text-blue-500" />
                    <h3 className="font-semibold text-lg">{template.name}</h3>
                  </div>
                  {template.is_builtin && (
                    <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
                      Built-in
                    </span>
                  )}
                </div>

                <p className="text-sm text-muted-foreground mb-4 line-clamp-2">
                  {template.description || 'No description'}
                </p>

                <div className="flex items-center gap-4 text-xs text-muted-foreground mb-4">
                  <span>{config?.inputs?.length || 0} inputs</span>
                </div>

                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1"
                    onClick={() => setSelectedTemplate(template)}
                  >
                    <Eye className="h-4 w-4 mr-1" />
                    View
                  </Button>
                  <Button
                    size="sm"
                    className="flex-1"
                    onClick={() => handleUseTemplate(template)}
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    Use
                  </Button>
                  {!template.is_builtin && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => deleteMutation.mutate(template.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {selectedTemplate && (
        <TemplateDetailModal
          template={selectedTemplate}
          onClose={() => setSelectedTemplate(null)}
          onUse={() => handleUseTemplate(selectedTemplate)}
        />
      )}

      {showCreateModal && (
        <JobCreateModal
          onClose={() => {
            setShowCreateModal(false)
          }}
        />
      )}
    </div>
  )
}
