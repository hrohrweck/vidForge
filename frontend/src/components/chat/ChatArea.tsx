import { useCallback, useRef, useState } from 'react'
import { Paperclip, X, FileText, Image, Music } from 'lucide-react'
import { useChatStore } from '../../stores/chat'
import type { Attachment } from '../../stores/chat'
import { chatApi } from '../../api/client'
import { ModelPicker } from './ModelPicker'

export type { Attachment }

function AttachmentChip({ att, onRemove }: { att: Attachment; onRemove: () => void }) {
  const icon =
    att.kind === 'image' ? (
      <Image className="h-3 w-3" />
    ) : att.kind === 'audio' ? (
      <Music className="h-3 w-3" />
    ) : (
      <FileText className="h-3 w-3" />
    )

  return (
    <div className="flex items-center gap-1 rounded-full bg-muted px-2 py-1 text-xs">
      {icon}
      <span className="max-w-[120px] truncate">{att.name}</span>
      <button
        onClick={onRemove}
        className="ml-1 rounded hover:bg-background"
        aria-label="Remove attachment"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  )
}

interface ChatAreaProps {
  conversationId: string
  onBack?: () => void
}

export function ChatArea({ conversationId }: ChatAreaProps) {
  const pendingAttachments = useChatStore((s) => s.pendingAttachments)
  const addAttachment = useChatStore((s) => s.addAttachment)
  const removeAttachment = useChatStore((s) => s.removeAttachment)
  const clearAttachments = useChatStore((s) => s.clearAttachments)
  const appendMessage = useChatStore((s) => s.appendMessage)
  const setStreaming = useChatStore((s) => s.setStreaming)
  const setStreamError = useChatStore((s) => s.setStreamError)

  const [input, setInput] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = useCallback(
    async (files: FileList | null) => {
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
    },
    [addAttachment, setStreamError]
  )

  const onFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      handleFileSelect(e.target.files)
      e.target.value = ''
    },
    [handleFileSelect]
  )

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }, [])

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
  }, [])

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      handleFileSelect(e.dataTransfer.files)
    },
    [handleFileSelect]
  )

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text && pendingAttachments.length === 0) return

    appendMessage(conversationId, {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      createdAt: new Date().toISOString(),
    })
    setInput('')

    const assistantMsg = {
      id: crypto.randomUUID(),
      role: 'assistant' as const,
      content: '',
      createdAt: new Date().toISOString(),
    }
    appendMessage(conversationId, assistantMsg)

    const attachmentIds = pendingAttachments.map((a) => a.id)
    clearAttachments()
    setStreaming(true)
    setStreamError(null)

    try {
      const stream = chatApi.streamMessage(
        conversationId,
        text,
        attachmentIds.length > 0 ? attachmentIds : undefined
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
  }, [
    input,
    pendingAttachments,
    conversationId,
    appendMessage,
    clearAttachments,
    setStreaming,
    setStreamError,
  ])

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend]
  )

  return (
    <div
      className="flex flex-col h-full"
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
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
  )
}