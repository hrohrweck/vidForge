import { Input } from '../ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

interface TimeframeSelectorProps {
  from: string
  to: string
  groupBy: string
  onChange: (from: string, to: string, groupBy: string) => void
}

export default function TimeframeSelector({ from, to, groupBy, onChange }: TimeframeSelectorProps) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <Input type="date" value={from} onChange={e => onChange(e.target.value, to, groupBy)} className="w-40" />
      <span className="text-muted-foreground">to</span>
      <Input type="date" value={to} onChange={e => onChange(from, e.target.value, groupBy)} className="w-40" />
      <Select value={groupBy} onValueChange={v => onChange(from, to, v)}>
        <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="hour">Hourly</SelectItem>
          <SelectItem value="day">Daily</SelectItem>
          <SelectItem value="month">Monthly</SelectItem>
        </SelectContent>
      </Select>
    </div>
  )
}
