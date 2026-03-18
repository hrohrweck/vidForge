import { useQuery } from '@tanstack/react-query'
import { templatesApi } from '../api/client'

export default function Templates() {
  const { data: templates, isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => templatesApi.list(),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Templates</h1>
        <p className="text-muted-foreground">
          Video generation templates for different use cases
        </p>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Loading templates...</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {templates?.map((template) => (
            <div key={template.id} className="border rounded-lg p-6">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-lg">{template.name}</h3>
                  {template.is_builtin && (
                    <span className="text-xs bg-secondary text-secondary-foreground px-2 py-0.5 rounded">
                      Built-in
                    </span>
                  )}
                </div>
              </div>
              <p className="text-sm text-muted-foreground mt-2">
                {template.description}
              </p>
              <div className="mt-4">
                <p className="text-xs text-muted-foreground">
                  Inputs: {(template.config as { inputs?: unknown[] }).inputs?.length || 0}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
