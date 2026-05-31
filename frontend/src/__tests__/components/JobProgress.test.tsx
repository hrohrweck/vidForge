import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import JobProgress from '../../components/chat/JobProgress'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  onmessage: ((ev: { data: string }) => void) | null = null
  closed = false
  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }
  close() {
    this.closed = true
  }
  send(_data: string) {}
}

describe('JobProgress', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
  })
  afterEach(() => {
    MockWebSocket.instances = []
    vi.unstubAllGlobals()
  })

  it('renders progress bar at 0% initially', () => {
    render(<JobProgress jobId="abc" />)
    const bar = screen.getByRole('progressbar')
    expect(bar).toBeTruthy()
    expect(bar.getAttribute('aria-valuenow')).toBe('0')
  })

  it('updates progress on WS message', () => {
    render(<JobProgress jobId="abc" />)
    const ws = MockWebSocket.instances[0]
    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({
          type: 'progress',
          job_id: 'abc',
          progress: 50,
          status: 'processing',
        }),
      })
    })
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('50')
  })

  it('stops on completed message and calls onComplete', () => {
    const onComplete = vi.fn()
    render(<JobProgress jobId="abc" onComplete={onComplete} />)
    const ws = MockWebSocket.instances[0]
    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({
          type: 'completed',
          job_id: 'abc',
          progress: 100,
          status: 'completed',
          output_path: '/x.mp4',
        }),
      })
    })
    expect(onComplete).toHaveBeenCalledWith({
      output_path: '/x.mp4',
      preview_path: undefined,
      status: 'completed',
    })
    expect(ws.closed).toBe(true)
  })

  it('treats status_update with status=completed as terminal', () => {
    const onComplete = vi.fn()
    render(<JobProgress jobId="abc" onComplete={onComplete} />)
    const ws = MockWebSocket.instances[0]
    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({
          type: 'status_update',
          job_id: 'abc',
          progress: 100,
          status: 'completed',
          output_path: '/x.mp4',
        }),
      })
    })
    expect(onComplete).toHaveBeenCalled()
    expect(ws.closed).toBe(true)
  })
})
