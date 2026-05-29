import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  createdAt: string
  attachments?: Array<{url: string; type: string; name?: string}>
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
  appendMessage: (convId: string, msg: Message) => void
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

      appendMessage: (convId, msg) =>
        set((state) => ({
          messages: {
            ...state.messages,
            [convId]: [...(state.messages[convId] || []), msg],
          },
        })),

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
        panelOpen: state.panelOpen,
      }),
    }
  )
)