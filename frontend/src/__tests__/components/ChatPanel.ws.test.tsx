import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChatPanel } from '../../components/chat/ChatPanel'
import { useChatStore } from '../../stores/chat'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  onmessage: ((ev: { data: string }) => void) | null = null
  closed = false
  constructor(public url: string) { MockWebSocket.instances.push(this) }
  close() { this.closed = true }
  send() {}
}

vi.mock('../../api/client', () => ({
  chatApi: {
    listMessages: vi.fn(async () => [
      { id: 'm1', role: 'assistant', content: 'Here is the result:', created_at: new Date().toISOString(), attachments: [] }
    ]),
    listConversations: vi.fn(async () => []),
    sendMessage: vi.fn(),
  },
}))

describe('ChatPanel chat WebSocket', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    const store = useChatStore as unknown as { persist?: { setOptions: (opts: Record<string, unknown>) => void } }
    store.persist?.setOptions({ storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} } })
    useChatStore.setState({
      conversations: [{ id: 'c1', title: 't', updatedAt: '', createdAt: '' }],
      selectedConversationId: 'c1',
      messages: { c1: [] },
    })
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    MockWebSocket.instances = []
  })

  it('appends message on chat_message_appended event and dedupes', async () => {
    const qc = new QueryClient()
    render(
      <QueryClientProvider client={qc}>
        <ChatPanel />
      </QueryClientProvider>
    )
    const ws = MockWebSocket.instances.find((w) => w.url.includes('/ws/chat/'))!
    const evt = { data: JSON.stringify({ type: 'chat_message_appended', message_id: 'm1' }) }
    await act(async () => { ws.onmessage?.(evt) })
    await act(async () => { ws.onmessage?.(evt) })
    await waitFor(() => {
      expect(useChatStore.getState().messages.c1.length).toBe(1)
    })
  })
})
