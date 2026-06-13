import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MessageBubble } from '../../MessageBubble'
import { ChatMessageList } from '../../ChatMessageList'
import type { Message } from '../../../../stores/chat'

vi.mock('../../../../api/client', () => ({
  jobsApi: {
    create: vi.fn().mockResolvedValue({ id: 'job-123' }),
    retry: vi.fn(),
    cancel: vi.fn(),
    generateAllImages: vi.fn(),
    generateAllVideos: vi.fn(),
    export: vi.fn(),
  },
  scenesApi: {
    generateAllImages: vi.fn(),
    generateAllVideos: vi.fn(),
    export: vi.fn(),
    cancel: vi.fn(),
    retry: vi.fn(),
  },
}))

import { jobsApi } from '../../../../api/client'

function makeMsg(overrides: Partial<Message> = {}): Message {
  return {
    id: 'msg-1',
    role: 'assistant',
    content: 'Here is a draft for your review.',
    createdAt: new Date().toISOString(),
    ...overrides,
  }
}

describe('MessageBubble with job_card attachment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a JobDraftCard when attachment kind is job_card and card_type is job_draft', () => {
    const msg = makeMsg({
      attachments: [
        {
          kind: 'job_card',
          card_type: 'job_draft',
          job_id: null,
          title: 'Job draft',
          data: {
            template: 'template-uuid',
            prompt: 'A cat riding a bicycle through a neon city',
            duration: 15,
            style: 'cyberpunk',
            aspect_ratio: '16:9',
          },
          actions: ['create'],
        },
      ],
    })

    render(<MessageBubble message={msg} />)

    expect(screen.getByDisplayValue('A cat riding a bicycle through a neon city')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create/i })).toBeInTheDocument()
  })

  it('calls jobsApi.create when Create is clicked', async () => {
    const msg = makeMsg({
      attachments: [
        {
          kind: 'job_card',
          card_type: 'job_draft',
          job_id: null,
          title: 'Job draft',
          data: {
            template: 'template-uuid',
            prompt: 'A cat riding a bicycle through a neon city',
            duration: 15,
            style: 'cyberpunk',
            aspect_ratio: '16:9',
          },
          actions: ['create'],
        },
      ],
    })

    render(<MessageBubble message={msg} />)

    fireEvent.click(screen.getByRole('button', { name: /create/i }))

    await waitFor(() => {
      expect(jobsApi.create).toHaveBeenCalledTimes(1)
    })

    expect(jobsApi.create).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'A cat riding a bicycle through a neon city',
        template_id: 'template-uuid',
        input_data: expect.objectContaining({
          prompt: 'A cat riding a bicycle through a neon city',
          duration: 15,
          style: 'cyberpunk',
          aspect_ratio: '16:9',
        }),
        auto_start: true,
      })
    )
  })
})

describe('ChatMessageList with job_card attachment', () => {
  it('renders a JobDraftCard for a job_draft attachment', () => {
    const msg = makeMsg({
      role: 'assistant',
      attachments: [
        {
          kind: 'job_card',
          card_type: 'job_draft',
          job_id: null,
          title: 'Job draft',
          data: {
            template: 'template-uuid',
            prompt: 'A cat riding a bicycle through a neon city',
            duration: 15,
            style: 'cyberpunk',
            aspect_ratio: '16:9',
          },
          actions: ['create'],
        },
      ],
    })

    render(<ChatMessageList messages={[msg]} />)

    expect(screen.getByDisplayValue('A cat riding a bicycle through a neon city')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create/i })).toBeInTheDocument()
  })
})
