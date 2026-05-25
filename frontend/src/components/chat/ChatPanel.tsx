import { useCallback, useEffect, useRef, useState } from 'react'
import { Paperclip, X, FileText, Image, Music } from 'lucide-react'
import { useChatStore } from '../../stores/chat'
import { generateId } from '../../lib/utils'
import type { Message, Attachment } from '../../stores/chat'
import { chatApi } from '../../api/client'
import { MessageBubble } from './MessageBubble'
import { ModelPicker } from './ModelPicker'

const PLACEHOLDER_MESSAGES: Message[] = [
  { id: '1', role: 'assistant', content: 'Hello! How can I help you today?', createdAt: new Date().toISOString() },
]

function AttachmentChip({ att, onRemove }: { att: Attachment; onRemove: () => void }) {
  const icon = att.kind === 'image' ? <Image className="h-3 w-3" /> :
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

export function ChatPanel() {
  const panelOpen = useChatStore((s) => s.panelOpen)
  const closePanel = useChatStore((s) => s.closePanel)
  const selectedConversationId = useChatStore((s) => s.selectedConversationId)
  const pendingAttachments = useChatStore((s) => s.pendingAttachments)
  const addAttachment = useChatStore((s) => s.addAttachment)
  const removeAttachment = useChatStore((s) => s.removeAttachment)
  const clearAttachments = useChatStore((s) => s.clearAttachments)
  const appendMessage = useChatStore((s) => s.appendMessage)
  const setStreaming = useChatStore((s) => s.setStreaming)
  const setStreamError = useChatStore((s) => s.setStreamError)
  const selectedModelId = useChatStore((s) => s.selectedModelId)

  const [input, setInput] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && panelOpen) closePanel()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [panelOpen, closePanel])

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

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }, [])

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    handleFileSelect(e.dataTransfer.files)
  }, [handleFileSelect])

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
          assistantMsg.content += delta
        } else if (event.event === 'error') {
          setStreamError((eventData.error as string) ?? 'Stream error')
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        setStreamError(err instanceof Error ? err.message : 'Stream failed')
      }
    } finally {
      setStreaming(false)
    }
  }, [input, pendingAttachments, selectedConversationId, appendMessage, clearAttachments, setStreaming, setStreamError])

  const onKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }, [handleSend])

  if (!panelOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-label="Chat panel"
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <div
        className="absolute inset-0 bg-black/50"
        onClick={closePanel}
      />
      <div className={`relative flex w-full max-w-[480px] flex-col bg-background shadow-xl transition-transform duration-300 ease-in-out md:max-w-[480px] ${dragOver ? 'ring-2 ring-primary' : ''}`}>
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="text-lg font-semibold">Chat</h2>
          <button
            onClick={closePanel}
            className="rounded p-1 hover:bg-muted"
            aria-label="Close chat"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {PLACEHOLDER_MESSAGES.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
        </div>

        <div className="border-t p-4">
          <ModelPicker />
          {pendingAttachments.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1">
              {pendingAttachments.map((att) => (
                <AttachmentChip
                  key={att.id}
                  att={att}
                  onRemove={() => removeAttachment(att.id)}
                />
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="rounded-md border p-2 hover:bg-muted disabled:opacity-50"
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
            <textarea
              ref={textareaRef}
              className="flex-1 resize-none rounded-md border px-3 py-2 text-sm"
              placeholder="Type a message..."
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
            />
            <button
              onClick={handleSend}
              disabled={isUploading || (!input.trim() && pendingAttachments.length === 0)}
              className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
            >
              Send
            </button>
          </div>
          {dragOver && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-primary/10">
              <p className="rounded-lg bg-background px-4 py-2 text-sm font-medium shadow-lg">
                Drop files here to attach
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
