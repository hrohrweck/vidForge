export interface JobCompletedCardProps {
  data: Record<string, unknown>
  jobId: string | null
}

export function JobCompletedCard({ data, jobId }: JobCompletedCardProps) {
  const result = data as {
    output_url: string | null
    preview_url: string | null
    thumbnail_url: string | null
  }

  const url = result.output_url ?? result.preview_url

  return (
    <div className="rounded-lg border bg-muted p-3 text-sm">
      <div className="mb-2 font-medium">Job completed</div>
      {jobId && <div className="mb-2 text-xs text-muted-foreground">Job ID: {jobId}</div>}

      {result.thumbnail_url && (
        <img
          src={result.thumbnail_url}
          alt="Completed job thumbnail"
          className="mb-2 max-h-40 w-full rounded object-cover"
        />
      )}

      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
        >
          Download video
        </a>
      ) : (
        <div className="text-xs text-muted-foreground">No output URL available.</div>
      )}
    </div>
  )
}
