import { useEffect, useCallback, useRef, useState } from 'react'
import { Paperclip, FileText, Image, Music, X, MessageSquare } from 'lucide-react'
import { generateId } from '../lib/utils'
import { useChatStore } from '../stores/chat'
import type { Message, Attachment } from '../stores/chat'
import { chatApi } from '../api/client'
import type { Message as ApiMessage } from '../api/client'
import { ConversationSidebar } from '../components/chat/ConversationSidebar'
import { ChatMessageList } from '../components/chat/ChatMessageList'
import { ModelPicker } from '../components/chat/ModelPicker'

function mapMessage(api: ApiMessage): Message {
  return {
    id: api.id,
    role: api.role,
    content: api.content,
    createdAt: api.created_at,
  }
}

function AttachmentChip({ att, onRemove }: { att: Attachment; onRemove: () => void }) {
  const icon =
    att.kind === 'image' ? <Image className="h-3 w-3" /> :
    att.kind === 'audio' ? <Music className="h-3 w-3" /> :
    <FileText className="h-3 w-3" />

  return (
    <div className="flex items-center gap-1 rounded-full bg-muted px-2 py-1 text-xs">
      {icon}
      <span className="max-w-[120px] truncate">{att.name}</span>
      <button onClick={onRemove} className="ml-1 rounded hover:bg-background" aria-label="Remove attachment">
        <X className="h-3 w-3" />
      </button>
    </div>
  )
}

export default function Chat() {
  const selectedConversationId = useChatStore((s) => s.selectedConversationId)
  const messages = useChatStore((s) =>
    selectedConversationId ? (s.messages[selectedConversationId] || []) : []
  )
  const pendingAttachments = useChatStore((s) => s.pendingAttachments)
  const addAttachment = useChatStore((s) => s.addAttachment)
  const removeAttachment = useChatStore((s) => s.removeAttachment)
  const clearAttachments = useChatStore((s) => s.clearAttachments)
  const appendMessage = useChatStore((s) => s.appendMessage)
  const setStreaming = useChatStore((s) => s.setStreaming)
  const setStreamError = useChatStore((s) => s.setStreamError)
  const streaming = useChatStore((s) => s.streaming)
  const streamError = useChatStore((s) => s.streamError)
  const updateStreamingMessage = useChatStore((s) => s.updateStreamingMessage)
  const selectConversation = useChatStore((s) => s.selectConversation)
  const selectedModelId = useChatStore((s) => s.selectedModelId)
  const refreshConversations = useChatStore((s) => s.refreshConversations)

  const [input, setInput] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

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

  const handleFileSelect = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setIsUploading(true)
    try {
      for (const file of Array.from(files)) {
        const result = await chatApi.uploadAttachment(file)
        addAttachment({
          id: result.attachment_id,
          kind: result.kind as Attachment['kind'],
          mimeType: result.mime_type,
          size: result.size,
          url: result.url,
          name: file.name,
        })
      }
    } catch (err) {
      setStreamError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setIsUploading(false)
    }
  }, [addAttachment, setStreamError])

  const onFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    handleFileSelect(e.target.files)
    e.target.value = ''
  }, [handleFileSelect])

  const handleNewChat = async () => {
    try {
      const apiConv = await chatApi.createConversation()
      const conv = { id: apiConv.id, title: apiConv.title || 'Untitled', createdAt: apiConv.created_at, updatedAt: apiConv.updated_at }
      selectConversation(conv.id)
    } catch (err) {
      console.error('Failed to create conversation:', err)
    }
  }

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text && pendingAttachments.length === 0) return
    if (!selectedConversationId) return

    const userMsg: Message = {
      id: generateId(),
      role: 'user',
      content: text,
      createdAt: new Date().toISOString(),
    }
    appendMessage(selectedConversationId, userMsg)
    setInput('')

    const attachmentData = pendingAttachments.map((a) => ({
      kind: a.kind,
      url: a.url,
      name: a.name,
    }))
    clearAttachments()
    setStreaming(true)
    setStreamError(null)

    try {
      const assistantMsg: Message = {
        id: generateId(),
        role: 'assistant',
        content: '',
        createdAt: new Date().toISOString(),
      }
      appendMessage(selectedConversationId, assistantMsg)

      const stream = chatApi.streamMessage(
        selectedConversationId,
        text,
        selectedModelId,
        attachmentData.length > 0 ? attachmentData : undefined
      )

      for await (const event of stream) {
        const eventData = event.data as Record<string, unknown>
        if (event.event === 'token') {
          const delta = (eventData.content as string) ?? ''
          updateStreamingMessage(selectedConversationId, delta)
        } else if (event.event === 'error') {
          setStreamError((eventData.reason as string) ?? (eventData.error as string) ?? 'Stream error')
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        setStreamError(err instanceof Error ? err.message : 'Stream failed')
      }
    } finally {
      setStreaming(false)
      refreshConversations()
    }
  }, [input, pendingAttachments, selectedConversationId, selectedModelId, appendMessage, updateStreamingMessage, clearAttachments, setStreaming, setStreamError, refreshConversations])

  const onKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }, [handleSend])

  return (
    <div className="flex h-full w-full">
      <div className="flex h-full w-full gap-[10px] p-[10px]">
        {/* Left sidebar — conversation history */}
        <div className="h-full w-72 shrink-0">
          <ConversationSidebar />
        </div>

        {/* Right content area */}
        {selectedConversationId ? (
          <div className="flex flex-1 flex-col gap-[10px] min-w-0 h-full">
            {/* Model picker at top */}
            <div className="rounded-[10px] border bg-card p-3 shrink-0">
              <ModelPicker />
            </div>

            {/* Chat messages — fills remaining space */}
            <div className="flex-1 rounded-[10px] border bg-card overflow-hidden min-h-0">
              <ChatMessageList messages={messages} streaming={streaming} />
            </div>

            {/* Input area — 50px height */}
            <div className="shrink-0">
              {streamError && (
                <div className="mb-[6px] rounded-[8px] bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  {streamError}
                </div>
              )}
              {pendingAttachments.length > 0 && (
                <div className="mb-[6px] flex flex-wrap gap-1">
                  {pendingAttachments.map((att) => (
                    <AttachmentChip
                      key={att.id}
                      att={att}
                      onRemove={() => removeAttachment(att.id)}
                    />
                  ))}
                </div>
              )}
              <div
                className="flex items-center gap-2 rounded-[10px] border bg-card px-3"
                style={{ height: '50px' }}
              >
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading || streaming}
                  className="flex shrink-0 items-center justify-center rounded-md border p-1.5 hover:bg-muted disabled:opacity-50"
                  aria-label="Attach file"
                  title="Attach file"
                >
                  <Paperclip className="h-4 w-4" />
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  multiple
                  onChange={onFileInputChange}
                  accept="image/*,audio/*,.txt,.md,.json,.yaml,.yml,.csv"
                />
                <input
                  ref={inputRef}
                  className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                  placeholder={streaming ? 'Waiting for response...' : 'Type a message...'}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onKeyDown}
                  disabled={streaming}
                />
                {streaming ? (
                  <div className="flex shrink-0 items-center gap-1.5 rounded-md bg-muted px-4 py-1.5 text-sm text-muted-foreground">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:200ms]" />
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:400ms]" />
                    <span className="ml-1">Processing</span>
                  </div>
                ) : (
                  <button
                    onClick={handleSend}
                    disabled={isUploading || (!input.trim() && pendingAttachments.length === 0)}
                    className="shrink-0 rounded-md bg-primary px-4 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
                  >
                    Send
                  </button>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 rounded-[10px] border bg-card">
            <MessageSquare className="h-12 w-12 text-muted-foreground/40" />
            <p className="text-muted-foreground">Select a conversation or start a new one</p>
            <button
              onClick={handleNewChat}
              className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90"
            >
              New Chat
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
