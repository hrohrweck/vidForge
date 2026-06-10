import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { usersApi } from '../api/client'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  createdAt: string
  attachments?: Array<{url: string; type?: string; name?: string; kind?: string; mime_type?: string}>
  toolCallId?: string
  jobId?: string | null
  mediaResult?: { kind: string; url: string; mime_type?: string }
}

export interface Conversation {
  id: string
  title: string
  createdAt: string
  updatedAt: string
}

export interface Attachment {
  id: string
  kind: 'image' | 'audio' | 'script' | 'text'
  mimeType: string
  size: number
  url: string
  name: string
}

interface ChatState {
  panelOpen: boolean
  selectedConversationId: string | null
  selectedModelId: string
  defaultModelId: string | null
  conversations: Conversation[]
  messages: Record<string, Message[]>
  streaming: boolean
  streamError: string | null
  autoCreateJobs: boolean
  pendingAttachments: Attachment[]
  openPanel: () => void
  closePanel: () => void
  togglePanel: () => void
  selectConversation: (id: string) => void
  setModel: (id: string) => void
  fetchDefaultModel: () => Promise<void>
  setDefaultModel: (id: string) => Promise<void>
  appendMessage: (convId: string, msg: Message) => void
  setMessages: (convId: string, msgs: Message[]) => void
  updateMessage: (convId: string, msgId: string, patch: Partial<Message>) => void
  updateStreamingMessage: (convId: string, delta: string) => void
  setStreaming: (streaming: boolean) => void
  setStreamError: (err: string | null) => void
  addAttachment: (att: Attachment) => void
  removeAttachment: (id: string) => void
  clearAttachments: () => void
  convRefreshKey: number
  refreshConversations: () => void
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      panelOpen: false,
      selectedConversationId: null,
      selectedModelId: 'qwen',
      defaultModelId: null,
      conversations: [],
      messages: {},
      streaming: false,
      streamError: null,
      autoCreateJobs: true,
      pendingAttachments: [],

      openPanel: () => set({ panelOpen: true }),
      closePanel: () => set({ panelOpen: false }),
      togglePanel: () => set((state) => ({ panelOpen: !state.panelOpen })),

      selectConversation: (id) => set({ selectedConversationId: id }),

      setModel: (id) => set({ selectedModelId: id }),

      fetchDefaultModel: async () => {
        try {
          const data = await usersApi.getDefaultChatModel()
          if (data.default_chat_model) {
            set({ defaultModelId: data.default_chat_model })
          }
        } catch {
          // Silently fail - default model is optional
        }
      },

      setDefaultModel: async (id) => {
        try {
          await usersApi.setDefaultChatModel(id)
          set({ defaultModelId: id })
        } catch (err) {
          console.error('Failed to set default model:', err)
          throw err
        }
      },

appendMessage: (convId, msg) =>
    set((state) => ({
      messages: {
        ...state.messages,
        [convId]: [...(state.messages[convId] || []), msg],
      },
    })),

  setMessages: (convId, msgs) =>
    set((state) => ({
      messages: {
        ...state.messages,
        [convId]: msgs,
      },
    })),

  updateMessage: (convId, msgId, patch) =>
    set((state) => {
      const convMessages = state.messages[convId] || []
      return {
        messages: {
          ...state.messages,
          [convId]: convMessages.map((m) =>
            m.id === msgId ? { ...m, ...patch } : m
          ),
        },
      }
    }),

  updateStreamingMessage: (convId, delta) =>
        set((state) => {
          const convMessages = state.messages[convId] || []
          if (convMessages.length === 0) return state
          const lastMsg = convMessages[convMessages.length - 1]
          if (lastMsg.role !== 'assistant') return state
          return {
            messages: {
              ...state.messages,
              [convId]: [
                ...convMessages.slice(0, -1),
                { ...lastMsg, content: lastMsg.content + delta },
              ],
            },
          }
        }),

      setStreaming: (streaming) => set({ streaming }),
      setStreamError: (err) => set({ streamError: err }),

      addAttachment: (att) =>
        set((state) => ({
          pendingAttachments: [...state.pendingAttachments, att],
        })),

      removeAttachment: (id) =>
        set((state) => ({
          pendingAttachments: state.pendingAttachments.filter((a) => a.id !== id),
        })),

      clearAttachments: () => set({ pendingAttachments: [] }),

      convRefreshKey: 0,
      refreshConversations: () => set((state) => ({ convRefreshKey: state.convRefreshKey + 1 })),
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        selectedModelId: state.selectedModelId,
        defaultModelId: state.defaultModelId,
        panelOpen: state.panelOpen,
      }),
    }
  )
)
// Expose store for E2E testing
if (typeof window !== 'undefined') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).__chatStore = useChatStore
}
