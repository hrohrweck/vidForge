import { useQuery } from '@tanstack/react-query'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import api from '../../api/client'

const COLORS = [
  '#8884d8',
  '#82ca9d',
  '#ffc658',
  '#ff7300',
  '#0088fe',
  '#00c49f',
  '#ffbb28',
  '#ff8042',
]

interface CostChartProps {
  from: string
  to: string
  groupBy: string
}

export default function CostChart({ from, to, groupBy }: CostChartProps) {
  const { data } = useQuery({
    queryKey: ['cost-time', from, to, groupBy],
    queryFn: () =>
      api
        .get('/dashboard/cost', { params: { from, to, group_by: groupBy } })
        .then((r) => r.data),
  })

  interface Bucket {
    timestamp: string
    model_id: string
    cost: number
  }
  const buckets: Bucket[] = data?.buckets ?? []

  const models: string[] = [...new Set(buckets.map((b) => b.model_id))]
  const chartData: Record<string, string | number>[] = buckets.reduce((acc: Record<string, string | number>[], b: Bucket) => {
    let entry = acc.find((e) => e.timestamp === b.timestamp)
    if (!entry) {
      entry = { timestamp: b.timestamp }
      acc.push(entry)
    }
    entry[b.model_id] = b.cost
    return acc
  }, [])

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="timestamp" tick={{ fontSize: 11 }} />
        <YAxis />
        <Tooltip />
        <Legend />
        {models.map((model, i) => (
          <Bar
            key={model}
            dataKey={model}
            stackId="cost"
            fill={COLORS[i % COLORS.length]}
            name={model}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}
