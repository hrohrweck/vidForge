import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../../test/utils'
import { MessageBubble } from '../../components/chat/MessageBubble'
import { ModelPicker } from '../../components/chat/ModelPicker'
import type { Message } from '../../stores/chat'

vi.mock('../../api/client', () => ({
  modelsApi: {
    getAvailableModels: vi.fn().mockResolvedValue({
      image_models: [],
      video_models: [],
      text_models: [
        {
          id: 'qwen', name: 'Qwen 3.6', description: 'Local LLM via Ollama',
          size_gb: 4, speed: 'fast', quality: 'great', license: 'Apache-2.0',
          provider: 'ollama', provider_type: 'ollama', default: true,
          capabilities: { outputs_text: true, accepts_text: true, accepts_image: true },
        },
        {
          id: 'llama', name: 'Llama 3.3', description: 'Local LLM',
          size_gb: 6, speed: 'medium', quality: 'great', license: 'open',
          provider: 'ollama', provider_type: 'ollama', default: false,
          capabilities: { outputs_text: true, accepts_text: true, accepts_image: true },
        },
        {
          id: 'glm', name: 'GLM 5.1', description: 'Cloud LLM via Poe',
          size_gb: 0, speed: 'fast', quality: 'excellent', license: 'proprietary',
          provider: 'poe', provider_type: 'poe', default: false,
          capabilities: { outputs_text: true, accepts_text: true, accepts_image: true },
        },
        {
          id: 'text-only-model', name: 'Text Only', description: 'Text input only, no images',
          size_gb: 4, speed: 'fast', quality: 'good', license: 'open',
          provider: 'ollama', provider_type: 'ollama', default: false,
          capabilities: { outputs_text: true, accepts_text: true, accepts_image: false },
        },
        {
          id: 'image-output-only', name: 'Image Output Only', description: 'Only generates images',
          size_gb: 12, speed: 'fast', quality: 'good', license: 'open',
          provider: 'poe', provider_type: 'poe', default: false,
          capabilities: { outputs_text: false, accepts_text: true, accepts_image: true },
        },
        {
          id: 'no-caps-model', name: 'No Capabilities', description: 'Legacy model with no caps',
          size_gb: 2, speed: 'fast', quality: 'good', license: 'open',
          provider: 'ollama', provider_type: 'ollama', default: false,
        },
      ],
    }),
    list: vi.fn(),
    get: vi.fn(),
    getModelPreferences: vi.fn(),
    updateModelPreferences: vi.fn(),
  },
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    refresh: vi.fn(),
    me: vi.fn().mockResolvedValue({ id: '1', email: 'test@example.com', is_active: true, is_superuser: false, groups: [], permissions: [] }),
    logout: vi.fn(),
  },
  jobsApi: { list: vi.fn().mockResolvedValue({ data: [] }), get: vi.fn(), create: vi.fn(), delete: vi.fn() },
  templatesApi: { list: vi.fn().mockResolvedValue({ data: [] }), get: vi.fn(), create: vi.fn() },
  stylesApi: { list: vi.fn().mockResolvedValue({ data: [] }) },
  providersApi: { list: vi.fn().mockResolvedValue({ data: [] }), status: vi.fn() },
  usersApi: { getSettings: vi.fn().mockResolvedValue({}), updateSettings: vi.fn() },
  healthApi: { getModels: vi.fn().mockResolvedValue({ models: {} }) },
}))

function makeMsg(overrides: Partial<Message> = {}): Message {
  return {
    id: 'msg-1',
    role: 'user',
    content: 'Hello',
    createdAt: new Date().toISOString(),
    ...overrides,
  }
}

describe('ModelPicker', () => {
  it('shows only models that accept text+image input and output text', async () => {
    renderWithProviders(<ModelPicker />)

    await waitFor(() => {
      expect(screen.queryByText('Loading models...')).not.toBeInTheDocument()
    })

    expect(screen.getByText('Qwen 3.6')).toBeInTheDocument()
    expect(screen.getByText('Llama 3.3')).toBeInTheDocument()
    expect(screen.getByText('GLM 5.1')).toBeInTheDocument()
    expect(screen.queryByText('Text Only')).not.toBeInTheDocument()
    expect(screen.queryByText('Image Output Only')).not.toBeInTheDocument()
    expect(screen.queryByText('No Capabilities')).not.toBeInTheDocument()
  })

  it('excludes models without accepts_image', async () => {
    renderWithProviders(<ModelPicker />)

    await waitFor(() => {
      expect(screen.queryByText('Loading models...')).not.toBeInTheDocument()
    })

    expect(screen.queryByText('Text Only')).not.toBeInTheDocument()
  })

  it('excludes models with outputs_text: false', async () => {
    renderWithProviders(<ModelPicker />)

    await waitFor(() => {
      expect(screen.queryByText('Loading models...')).not.toBeInTheDocument()
    })

    expect(screen.queryByText('Image Output Only')).not.toBeInTheDocument()
  })

  it('excludes models with no capabilities defined', async () => {
    renderWithProviders(<ModelPicker />)

    await waitFor(() => {
      expect(screen.queryByText('Loading models...')).not.toBeInTheDocument()
    })

    expect(screen.queryByText('No Capabilities')).not.toBeInTheDocument()
  })
})

describe('MessageBubble', () => {
  describe('timestamp', () => {
    it('displays formatted timestamp on message bubble', () => {
      const msg = makeMsg({ createdAt: new Date().toISOString() })
      render(<MessageBubble message={msg} />)

      const ts = screen.getByTitle(new Date(msg.createdAt).toLocaleString())
      expect(ts).toBeInTheDocument()
    })

    it('renders "just now" for very recent messages', () => {
      const msg = makeMsg({ createdAt: new Date().toISOString() })
      render(<MessageBubble message={msg} />)
      expect(screen.getByText(/just now/)).toBeInTheDocument()
    })

    it('renders relative minute format for older messages', () => {
      const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString()
      const msg = makeMsg({ createdAt: fiveMinAgo })
      render(<MessageBubble message={msg} />)
      expect(screen.getByText(/5m ago/)).toBeInTheDocument()
    })
  })

  describe('user message alignment', () => {
    it('has right-aligned timestamp for user messages', () => {
      const msg = makeMsg({ role: 'user' })
      render(<MessageBubble message={msg} />)
      const ts = screen.getByTitle(new Date(msg.createdAt).toLocaleString())
      expect(ts.className).toContain('text-right')
    })

    it('has left-aligned timestamp for assistant messages', () => {
      const msg = makeMsg({ role: 'assistant' })
      render(<MessageBubble message={msg} />)
      const ts = screen.getByTitle(new Date(msg.createdAt).toLocaleString())
      expect(ts.className).toContain('text-left')
    })

    it('renders user message bubble right-aligned', () => {
      const msg = makeMsg({ role: 'user' })
      const { container } = render(<MessageBubble message={msg} />)
      const wrapper = container.firstElementChild!
      expect(wrapper.className).toContain('items-end')
    })

    it('renders assistant message bubble left-aligned', () => {
      const msg = makeMsg({ role: 'assistant' })
      const { container } = render(<MessageBubble message={msg} />)
      const wrapper = container.firstElementChild!
      expect(wrapper.className).toContain('items-start')
    })
  })

  describe('media attachments', () => {
    it('renders image attachment as thumbnail', () => {
      const msg = makeMsg({
        attachments: [
          { url: 'https://example.com/img.png', type: 'image/png', name: 'screenshot.png' },
        ],
      })
      render(<MessageBubble message={msg} />)

      const img = screen.getByAltText('screenshot.png')
      expect(img).toBeInTheDocument()
      expect(img.tagName).toBe('IMG')
      expect(img).toHaveAttribute('src', 'https://example.com/img.png')
    })

    it('renders image thumbnail with click handler to open in new tab', () => {
      const msg = makeMsg({
        attachments: [
          { url: 'https://example.com/img.png', type: 'image/jpeg', name: 'photo.jpg' },
        ],
      })
      render(<MessageBubble message={msg} />)

      const img = screen.getByAltText('photo.jpg')
      expect(img.className).toContain('cursor-pointer')
      expect(img).toHaveAttribute('src', 'https://example.com/img.png')
    })

    it('does not render attachments when none exist', () => {
      const msg = makeMsg({ attachments: undefined })
      const { container } = render(<MessageBubble message={msg} />)

      const imgs = container.querySelectorAll('img')
      expect(imgs.length).toBe(0)
    })

    it('renders attachment as download link for non-image types', () => {
      const msg = makeMsg({
        attachments: [
          { url: 'https://example.com/doc.pdf', type: 'application/pdf', name: 'doc.pdf' },
        ],
      })
      render(<MessageBubble message={msg} />)

      const link = screen.getByText('doc.pdf')
      expect(link.tagName).toBe('A')
      expect(link).toHaveAttribute('href', 'https://example.com/doc.pdf')
      expect(link).toHaveAttribute('target', '_blank')
    })

    it('renders multiple attachments', () => {
      const msg = makeMsg({
        attachments: [
          { url: 'https://example.com/a.png', type: 'image/png', name: 'a.png' },
          { url: 'https://example.com/b.png', type: 'image/png', name: 'b.png' },
        ],
      })
      render(<MessageBubble message={msg} />)

      expect(screen.getByAltText('a.png')).toBeInTheDocument()
      expect(screen.getByAltText('b.png')).toBeInTheDocument()
    })
  })
})
