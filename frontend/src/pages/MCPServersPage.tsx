import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, RefreshCw, Pencil, Trash2, Play, X } from 'lucide-react'
import { mcpAdminApi, MCPServer, MCPServerCreate } from '../api/client'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'

interface FormState {
  id: string | null
  name: string
  command: string
  args: string
  envKeys: string
  isActive: boolean
}

const blank: FormState = { id: null, name: '', command: '', args: '', envKeys: '', isActive: true }

export default function MCPServersPage() {
  const qc = useQueryClient()
  const [show, setShow] = useState(false)
  const [form, setForm] = useState<FormState>(blank)
  const [err, setErr] = useState('')
  const [testMsg, setTestMsg] = useState<Record<string, string>>({})
  const [toolsCount, setToolsCount] = useState<Record<string, number>>({})

  const { data: servers, isLoading, refetch } = useQuery<MCPServer[]>({
    queryKey: ['mcp-servers'],
    queryFn: mcpAdminApi.listServers,
  })

  const create = useMutation({ mutationFn: mcpAdminApi.createServer, onSuccess: () => { qc.invalidateQueries({ queryKey: ['mcp-servers'] }); setShow(false); setForm(blank) }, onError: (e: unknown) => setErr(e instanceof Error ? e.message : 'Failed') })
  const update = useMutation({ mutationFn: ({ id, data }: { id: string; data: MCPServerCreate }) => mcpAdminApi.updateServer(id, data), onSuccess: () => { qc.invalidateQueries({ queryKey: ['mcp-servers'] }); setShow(false); setForm(blank) }, onError: (e: unknown) => setErr(e instanceof Error ? e.message : 'Failed') })
  const remove = useMutation({ mutationFn: mcpAdminApi.deleteServer, onSuccess: () => qc.invalidateQueries({ queryKey: ['mcp-servers'] }) })
  const test = useMutation({ mutationFn: async (id: string) => { const t = await mcpAdminApi.listServerTools(id); return { id, msg: `OK – ${t.length} tool(s)` } }, onSuccess: (r) => setTestMsg((p) => ({ ...p, [r.id]: r.msg })), onError: (e: unknown, id) => setTestMsg((p) => ({ ...p, [id]: String(e instanceof Error ? e.message : 'Failed') })) })

  const loadTools = async (id: string) => {
    if (toolsCount[id] !== undefined) return
    const t = await mcpAdminApi.listServerTools(id)
    setToolsCount((p) => ({ ...p, [id]: t.length }))
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault(); setErr('')
    if (!form.name.trim()) { setErr('Name required'); return }
    if (!form.command.trim()) { setErr('Command required'); return }
    const env = form.envKeys ? Object.fromEntries(form.envKeys.split('\n').filter(l => l.includes('=')).map(l => { const [k, ...v] = l.split('='); return [k.trim(), v.join('=').trim()] })) : undefined
    const args = form.args ? form.args.split('\n').filter(Boolean) : undefined
    const payload: MCPServerCreate = { name: form.name.trim(), command: form.command.trim(), env, args }
    form.id ? update.mutate({ id: form.id, data: payload }) : create.mutate(payload)
  }

  const del = (id: string, name: string) => { if (window.confirm(`Delete "${name}"?`)) remove.mutate(id) }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">MCP Servers</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}><RefreshCw className="w-4 h-4 mr-2" />Refresh</Button>
          <Button size="sm" onClick={() => { setForm(blank); setErr(''); setShow(true) }}><Plus className="w-4 h-4 mr-2" />Add Server</Button>
        </div>
      </div>

      {isLoading ? <div className="text-center py-10 text-muted-foreground">Loading…</div>
       : !servers?.length ? <div className="text-center py-10 text-muted-foreground">No servers configured.</div>
       : <div className="border rounded-md">
         <table className="w-full">
           <thead className="bg-muted/50">
             <tr><th className="text-left px-4 py-3 text-sm font-medium">Name</th><th className="text-left px-4 py-3 text-sm font-medium">Command</th><th className="text-center px-4 py-3 text-sm font-medium">Enabled</th><th className="text-center px-4 py-3 text-sm font-medium">Tools</th><th className="text-center px-4 py-3 text-sm font-medium">Actions</th></tr>
           </thead>
           <tbody className="divide-y">
             {servers.map(s => (
               <tr key={s.id} className="hover:bg-muted/30">
                 <td className="px-4 py-3 font-medium">{s.name}</td>
                 <td className="px-4 py-3 font-mono text-sm">{s.command}</td>
                 <td className="px-4 py-3 text-center"><Badge variant={s.is_active ? 'default' : 'secondary'}>{s.is_active ? 'Yes' : 'No'}</Badge></td>
                 <td className="px-4 py-3 text-center"><button className="text-primary hover:underline" onClick={() => loadTools(s.id)}>{toolsCount[s.id] ?? '-'}</button></td>
                 <td className="px-4 py-3">
                   <div className="flex items-center justify-center gap-1">
                     <Button variant="ghost" size="sm" onClick={() => test.mutate(s.id)} disabled={test.isPending} title="Test server" aria-label="Test server"><Play className="w-4 h-4" /></Button>
                     <Button variant="ghost" size="sm" onClick={() => { setForm({ id: s.id, name: s.name, command: s.command, args: s.args?.join('\n') || '', envKeys: s.env_keys?.join('\n') || '', isActive: s.is_active }); setErr(''); setShow(true) }} title="Edit server" aria-label="Edit server"><Pencil className="w-4 h-4" /></Button>
                     <Button variant="ghost" size="sm" onClick={() => del(s.id, s.name)} disabled={remove.isPending} title="Delete server" aria-label="Delete server"><Trash2 className="w-4 h-4 text-destructive" /></Button>
                   </div>
                 </td>
               </tr>
             ))}
           </tbody>
         </table>
         {Object.entries(testMsg).filter(([, m]) => m).map(([id, msg]) => (
           <div key={id} className={`px-4 py-2 text-sm ${msg.startsWith('OK') ? 'bg-green-500/10 text-green-600' : 'bg-red-500/10 text-red-600'}`}>{msg}</div>
         ))}
       </div>}

      {show && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background rounded-lg shadow-lg w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">{form.id ? 'Edit Server' : 'Add Server'}</h2>
              <button onClick={() => setShow(false)} className="text-muted-foreground hover:text-foreground" title="Close" aria-label="Close"><X className="w-5 h-5" /></button>
            </div>
            <form onSubmit={submit} className="space-y-4">
              <div><label className="block text-sm font-medium mb-1">Name *</label><input type="text" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="w-full px-3 py-2 border rounded-md bg-background text-sm" /></div>
              <div><label className="block text-sm font-medium mb-1">Command *</label><input type="text" value={form.command} onChange={e => setForm({ ...form, command: e.target.value })} className="w-full px-3 py-2 border rounded-md bg-background text-sm font-mono" /></div>
              <div><label className="block text-sm font-medium mb-1">Args (one per line)</label><textarea value={form.args} onChange={e => setForm({ ...form, args: e.target.value })} className="w-full px-3 py-2 border rounded-md bg-background text-sm font-mono" rows={2} /></div>
              <div><label className="block text-sm font-medium mb-1">Env (KEY=value, one per line)</label><textarea value={form.envKeys} onChange={e => setForm({ ...form, envKeys: e.target.value })} className="w-full px-3 py-2 border rounded-md bg-background text-sm font-mono" rows={2} /></div>
              <div className="flex items-center gap-2"><input type="checkbox" id="active" checked={form.isActive} onChange={e => setForm({ ...form, isActive: e.target.checked })} /><label htmlFor="active" className="text-sm">Enabled</label></div>
              {err && <div className="text-sm text-destructive">{err}</div>}
              <div className="flex justify-end gap-2 pt-2"><Button type="button" variant="outline" onClick={() => setShow(false)}>Cancel</Button><Button type="submit" disabled={create.isPending || update.isPending}>{form.id ? 'Save' : 'Create'}</Button></div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}