import { useQuery } from '@tanstack/react-query'
import { BarChart3 } from 'lucide-react'
import { chatApi } from '../../api/client'

interface TokenUsageItem {
  model_id: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  estimated_cost: number | null
  message_count: number
}

interface TokenUsageResponse {
  items: TokenUsageItem[]
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toString()
}

export default function TokenUsageHistogram() {
  const { data, isLoading } = useQuery<TokenUsageResponse>({
    queryKey: ['token-usage'],
    queryFn: () => chatApi.getTokenUsage(),
  })

  const items = data?.items ?? []
  const maxTokens = Math.max(...items.map((i) => i.total_tokens), 1)

  return (
    <div className="border rounded-lg bg-card text-card-foreground shadow-sm p-4">
      <div className="flex items-center gap-2 mb-4">
        <BarChart3 className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-xl font-semibold">Token Usage by Model</h2>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground text-sm">Loading...</p>
      ) : items.length === 0 ? (
        <p className="text-muted-foreground text-sm">No usage yet</p>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <div key={item.model_id} className="flex items-center gap-3">
              <span className="w-32 text-sm truncate font-mono" title={item.model_id}>
                {item.model_id}
              </span>
              <div className="flex-1 h-5 bg-muted rounded overflow-hidden">
                <div
                  className="h-full bg-primary rounded"
                  style={{ width: `${(item.total_tokens / maxTokens) * 100}%` }}
                />
              </div>
              <span className="w-20 text-sm text-right text-muted-foreground">
                {formatNumber(item.total_tokens)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}