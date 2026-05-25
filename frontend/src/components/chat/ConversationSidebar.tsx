import { useEffect, useState } from 'react'
import { MessageSquare, Plus, Trash2 } from 'lucide-react'
import { useChatStore } from '../../stores/chat'
import { chatApi } from '../../api/client'
import type { Conversation as ApiConversation } from '../../api/client'
import type { Conversation } from '../../stores/chat'

export function ConversationSidebar() {
  const selectedConversationId = useChatStore((s) => s.selectedConversationId)
  const selectConversation = useChatStore((s) => s.selectConversation)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [deleting, setDeleting] = useState<string | null>(null)

  useEffect(() => {
    chatApi.listConversations().then((data) => {
      setConversations(
        data.map((api: ApiConversation) => ({
          id: api.id,
          title: api.title || 'Untitled',
          createdAt: api.created_at,
          updatedAt: api.updated_at,
        }))
      )
    }).catch((err) => console.error('Failed to load conversations:', err))
  }, [])

  const handleNewChat = async () => {
    try {
      const apiConv = await chatApi.createConversation()
      const conv = { id: apiConv.id, title: apiConv.title || 'Untitled', createdAt: apiConv.created_at, updatedAt: apiConv.updated_at }
      setConversations((prev) => [conv, ...prev])
      selectConversation(conv.id)
    } catch (err) {
      console.error('Failed to create conversation:', err)
    }
  }

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (!confirm('Delete this conversation?')) return
    setDeleting(id)
    try {
      await chatApi.deleteConversation(id)
      setConversations((prev) => prev.filter((c) => c.id !== id))
      if (selectedConversationId === id) selectConversation('')
    } catch (err) {
      console.error('Failed to delete conversation:', err)
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div className="flex h-full flex-col rounded-[10px] border bg-card overflow-hidden">
      <div className="border-b p-3">
        <button
          onClick={handleNewChat}
          className="flex w-full items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {conversations.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">No conversations yet.</p>
        ) : (
          <ul className="p-2">
            {conversations.map((conv) => (
              <li
                key={conv.id}
                onClick={() => selectConversation(conv.id)}
                className={`group flex items-center gap-2 rounded-md px-3 py-2 cursor-pointer hover:bg-muted ${selectedConversationId === conv.id ? 'bg-muted' : ''}`}
              >
                <MessageSquare className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="flex-1 min-w-0">
                  <p className="truncate text-sm font-medium">{conv.title}</p>
                  <p className="text-xs text-muted-foreground">{new Date(conv.updatedAt).toLocaleDateString()}</p>
                </div>
                <button
                  onClick={(e) => handleDelete(e, conv.id)}
                  disabled={deleting === conv.id}
                  className="shrink-0 rounded p-1 hover:bg-destructive/10 hover:text-destructive opacity-0 group-hover:opacity-100"
                  aria-label="Delete conversation"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
