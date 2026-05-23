interface JobDraftCardProps {
  draftId: string
  templateId: string
  params: object
  estimatedCost?: number
  onConfirm: () => void
  onEdit: () => void
  onCancel: () => void
  disabled?: boolean
}

export function JobDraftCard({
  draftId,
  templateId,
  params,
  estimatedCost,
  onConfirm,
  onEdit,
  onCancel,
  disabled,
}: JobDraftCardProps) {
  return (
    <div className="mb-3 rounded-lg border border-border bg-background px-4 py-3">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-sm font-medium text-foreground">Template: {templateId}</span>
          {estimatedCost !== undefined && (
            <span className="ml-2 text-xs text-muted-foreground">
              Est. cost: ${estimatedCost.toFixed(4)}
            </span>
          )}
        </div>
        <span className="text-xs text-muted-foreground">Draft: {draftId}</span>
      </div>

      <div className="mt-2">
        <p className="text-xs text-muted-foreground">Parameters:</p>
        <pre className="mt-1 overflow-x-auto rounded bg-muted p-2 text-xs">
          {JSON.stringify(params, null, 2)}
        </pre>
      </div>

      <div className="mt-3 flex gap-2">
        <button
          onClick={onConfirm}
          disabled={disabled}
          className="rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          Create
        </button>
        <button
          onClick={onEdit}
          disabled={disabled}
          className="rounded bg-muted px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted/80 disabled:opacity-50"
        >
          Edit
        </button>
        <button
          onClick={onCancel}
          disabled={disabled}
          className="rounded bg-muted px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted/80 disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}