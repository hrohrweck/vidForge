import { useEffect } from 'react'
import { useChatStore } from '../stores/chat'
import type { Message } from '../stores/chat'
import { chatApi } from '../api/client'
import type { Message as ApiMessage } from '../api/client'
import { ConversationSidebar } from '../components/chat/ConversationSidebar'
import { ChatMessageList } from '../components/chat/ChatMessageList'
import { ChatArea } from '../components/chat/ChatArea'

function mapMessage(api: ApiMessage): Message {
  return {
    id: api.id,
    role: api.role,
    content: api.content,
    createdAt: api.created_at,
  }
}

export default function Chat() {
  const selectedConversationId = useChatStore((s) => s.selectedConversationId)
  const messages = useChatStore((s) =>
    selectedConversationId ? (s.messages[selectedConversationId] || []) : []
  )
  const appendMessage = useChatStore((s) => s.appendMessage)

  useEffect(() => {
    if (!selectedConversationId) return

    const loadMessages = async () => {
      try {
        const apiMsgs = await chatApi.listMessages(selectedConversationId)
        const existing = useChatStore.getState().messages[selectedConversationId]
        if (!existing || existing.length === 0) {
          apiMsgs.map(mapMessage).forEach((msg) => appendMessage(selectedConversationId, msg))
        }
      } catch (err) {
        console.error('Failed to load messages:', err)
      }
    }

    loadMessages()
  }, [selectedConversationId, appendMessage])

  return (
    <div className="flex h-full overflow-hidden">
      <div className="w-1/4 shrink-0">
        <ConversationSidebar />
      </div>
      <div className="flex flex-1 flex-col">
        {selectedConversationId ? (
          <>
            <ChatMessageList messages={messages} />
            <ChatArea conversationId={selectedConversationId} />
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            <p>Select a conversation or start a new one</p>
          </div>
        )}
      </div>
    </div>
  )
}