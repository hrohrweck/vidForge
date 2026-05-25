import { useCallback, useRef, useState } from 'react'
import { useChatStore, type Message } from '../stores/chat'
import { chatApi } from '../api/client'
import api from '../api/client'
import { generateId } from '../lib/utils'

export interface UseChatReturn {
  messages: Message[]
  streamingMessage: string
  sendMessage: (content: string, attachments?: Array<{ kind: string; url: string; name?: string }>) => Promise<void>
  confirmJobDraft: (draftId: string) => Promise<void>
  cancelDraft: () => void
  isStreaming: boolean
  error: string | null
}

export function useChat(conversationId: string | null): UseChatReturn {
  const [streamingMessage, setStreamingMessage] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toolMessages, setToolMessages] = useState<Message[]>([])
  const abortControllerRef = useRef<AbortController | null>(null)

  const storeMessages = useChatStore((s) => s.messages[conversationId ?? ''] ?? [])
  const appendMessage = useChatStore((s) => s.appendMessage)
  const updateStreamingMessage = useChatStore((s) => s.updateStreamingMessage)
  const setStreaming = useChatStore((s) => s.setStreaming)
  const setStreamError = useChatStore((s) => s.setStreamError)
  const clearAttachments = useChatStore((s) => s.clearAttachments)

  const messages = [...storeMessages, ...toolMessages]

  const cleanup = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
  }, [])

  const finalizeStreaming = useCallback(
    (finalContent: string) => {
      if (!conversationId) return
      const convMessages = storeMessages
      if (convMessages.length > 0) {
        const lastMsg = convMessages[convMessages.length - 1]
        if (lastMsg.role === 'assistant') {
          updateStreamingMessage(conversationId, finalContent)
          return
        }
      }
      appendMessage(conversationId, {
        id: generateId(),
        role: 'assistant',
        content: finalContent,
        createdAt: new Date().toISOString(),
      })
    },
    [conversationId, storeMessages, updateStreamingMessage, appendMessage]
  )

  const sendMessage = useCallback(
    async (content: string, attachments?: Array<{ kind: string; url: string; name?: string }>) => {
      if (!conversationId) return

      cleanup()
      setError(null)
      setIsStreaming(true)
      setStreaming(true)
      setStreamError(null)
      setStreamingMessage('')
      setToolMessages([])

      const controller = new AbortController()
      abortControllerRef.current = controller

      appendMessage(conversationId, {
        id: generateId(),
        role: 'assistant',
        content: '',
        createdAt: new Date().toISOString(),
      })

      const modelId = useChatStore.getState().selectedModelId
      let accumulatedDelta = ''

      try {
        const events = chatApi.streamMessage(
          conversationId,
          content,
          modelId,
          attachments,
          controller.signal
        )

        for await (const event of events) {
          const eventData = event.data as Record<string, unknown>
          switch (event.event) {
            case 'token': {
              const delta = (eventData.content as string) ?? ''
              accumulatedDelta += delta
              updateStreamingMessage(conversationId, delta)
              setStreamingMessage((prev) => prev + delta)
              break
            }
            case 'tool_call_start': {
              const toolMsg = {
                id: generateId(),
                role: 'tool' as const,
                content: JSON.stringify({
                  tool_call_id: eventData.tool_call_id,
                  name: eventData.name,
                  arguments: eventData.arguments,
                }),
                createdAt: new Date().toISOString(),
              }
              setToolMessages((prev) => [...prev, toolMsg])
              break
            }
            case 'tool_call_result': {
              const toolMsg = {
                id: generateId(),
                role: 'tool' as const,
                content: JSON.stringify({
                  tool_call_id: eventData.tool_call_id,
                  output: eventData.output,
                  error: eventData.error,
                }),
                createdAt: new Date().toISOString(),
              }
              setToolMessages((prev) => [...prev, toolMsg])
              break
            }
            case 'error': {
              const errorMsg = (eventData.reason as string) ?? (eventData.error as string) ?? 'Unknown streaming error'
              setError(errorMsg)
              setStreamError(errorMsg)
              break
            }
          }
        }

        finalizeStreaming(accumulatedDelta)
        clearAttachments()
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
          finalizeStreaming(accumulatedDelta)
        } else {
          const msg = err instanceof Error ? err.message : 'Failed to send message'
          setError(msg)
          setStreamError(msg)
        }
      } finally {
        setIsStreaming(false)
        setStreaming(false)
        abortControllerRef.current = null
      }
    },
    [
      conversationId,
      cleanup,
      appendMessage,
      updateStreamingMessage,
      finalizeStreaming,
      clearAttachments,
      setStreaming,
      setStreamError,
      storeMessages,
    ]
  )

  const confirmJobDraft = useCallback(
    async (draftId: string) => {
      if (!conversationId) return
      await api.post(`/chat/conversations/${conversationId}/messages`, {
        confirm_draft_id: draftId,
      })
    },
    [conversationId]
  )

  const cancelDraft = useCallback(() => {}, [])

  return {
    messages,
    streamingMessage,
    sendMessage,
    confirmJobDraft,
    cancelDraft,
    isStreaming,
    error,
  }
}
