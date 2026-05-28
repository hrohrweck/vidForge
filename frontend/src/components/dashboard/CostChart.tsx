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

  const buckets: any[] = data?.buckets ?? []

  const models: string[] = [...new Set(buckets.map((b: any) => b.model_id))]
  const chartData: Record<string, any>[] = buckets.reduce((acc: any[], b: any) => {
    let entry = acc.find((e) => e.timestamp === b.timestamp)
    if (!entry) {
      entry = { timestamp: b.timestamp }
      acc.push(entry)
    }
    entry[b.model_id] = b.cost
    return acc
  }, [] as any[])

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
