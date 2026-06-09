import { describe, it, expect } from 'vitest'
import { parseThinking } from '../../components/chat/ChatMessageList'

describe('parseThinking', () => {
  describe('<think> format (DeepSeek/Ollama)', () => {
    it('should parse basic <think> tag', () => {
      const input = '<think>Let me think about this</think>The answer is 42'
      const result = parseThinking(input)
      expect(result.thinking).toBe('Let me think about this')
      expect(result.answer).toBe('The answer is 42')
    })

    it('should handle <think> with newlines and whitespace', () => {
      const input = '<think>\n  reasoning here\n</think>\n\nanswer here'
      const result = parseThinking(input)
      expect(result.thinking).toBe('reasoning here')
      expect(result.answer).toBe('answer here')
    })

    it('should handle multiple <think> blocks (3+ tags)', () => {
      const input = '<think>reasoning part 1</think><think>reasoning part 2</think><think>reasoning part 3</think>final answer'
      const result = parseThinking(input)
      expect(result.thinking).toContain('reasoning part 1')
      expect(result.thinking).toContain('reasoning part 2')
      expect(result.thinking).toContain('reasoning part 3')
      expect(result.answer).toBe('final answer')
    })

    it('should not extract partial <think> tag during streaming', () => {
      const input = 'partial<think>reasoning without closing tag'
      const result = parseThinking(input)
      expect(result.thinking).toBe('')
      expect(result.answer).toBe('partial<think>reasoning without closing tag')
    })

    it('should handle <think> with content before it', () => {
      const input = 'Some prefix<think>thinking content</think>the answer'
      const result = parseThinking(input)
      expect(result.thinking).toContain('Some prefix')
      expect(result.thinking).toContain('thinking content')
      expect(result.answer).toBe('the answer')
    })
  })

  describe('【thinking】 format (Qwen)', () => {
    it('should parse Qwen thinking format', () => {
      const input = '【thinking】Let me analyze this【/thinking】The result is correct'
      const result = parseThinking(input)
      expect(result.thinking).toBe('Let me analyze this')
      expect(result.answer).toBe('The result is correct')
    })

    it('should handle Qwen format with newlines', () => {
      const input = '【thinking】\n  analysis\n  more analysis\n【/thinking】\n\nfinal answer'
      const result = parseThinking(input)
      expect(result.thinking).toContain('analysis')
      expect(result.thinking).toContain('more analysis')
      expect(result.answer).toBe('final answer')
    })
  })

  describe('Inline thinking format (GLM/Poe)', () => {
    it('should parse GLM/Poe inline thinking with Generate Response marker', () => {
      const input = `Thinking...
Let me consider the options.
> This is a blockquote reasoning line

Generate Response. (Proceed to output).
Here is the actual answer.`
      const result = parseThinking(input)
      expect(result.thinking).toContain('Thinking')
      expect(result.thinking).toContain('consider the options')
      expect(result.answer).toBe('Here is the actual answer.')
    })

    it('should handle inline thinking with Final Answer marker', () => {
      const input = `Thinking about this problem...
Analyzing the data...

Final Answer
The solution is X`
      const result = parseThinking(input)
      expect(result.thinking).toContain('Thinking about this problem')
      expect(result.answer).toBe('The solution is X')
    })

    it('should handle inline thinking with Actual Answer marker', () => {
      const input = `Thinking...
Reasoning step 1
Reasoning step 2

Actual Answer
The answer is 42`
      const result = parseThinking(input)
      expect(result.thinking).toContain('Reasoning step 1')
      expect(result.answer).toBe('The answer is 42')
    })
  })

  describe('Edge cases', () => {
    it('should return empty thinking when no thinking format detected', () => {
      const input = 'just a plain answer with no thinking'
      const result = parseThinking(input)
      expect(result.thinking).toBe('')
      expect(result.answer).toBe('just a plain answer with no thinking')
    })

    it('should handle empty string', () => {
      const result = parseThinking('')
      expect(result.thinking).toBe('')
      expect(result.answer).toBe('')
    })

    it('should handle thinking with code blocks', () => {
      const input = `<think>
Let me write some code:
\`\`\`python
def hello():
    print("world")
\`\`\`
</think>
Here is the code you requested`
      const result = parseThinking(input)
      expect(result.thinking).toContain('```python')
      expect(result.thinking).toContain('def hello()')
      expect(result.answer).toBe('Here is the code you requested')
    })

    it('should handle answer with markdown formatting', () => {
      const input = '<think>thinking</think># Heading\n\n**Bold text** and *italic*'
      const result = parseThinking(input)
      expect(result.thinking).toBe('thinking')
      expect(result.answer).toContain('# Heading')
      expect(result.answer).toContain('**Bold text**')
      expect(result.answer).toContain('*italic*')
    })

    it('should handle very long thinking content (1000+ chars)', () => {
      const longThinking = 'A'.repeat(1200)
      const input = `<think>${longThinking}</think>Short answer`
      const result = parseThinking(input)
      expect(result.thinking.length).toBeGreaterThan(1000)
      expect(result.thinking).toBe(longThinking)
      expect(result.answer).toBe('Short answer')
    })

    it('should handle thinking with multiple paragraphs', () => {
      const input = `<think>
First paragraph of thinking.

Second paragraph with more details.

Third paragraph concluding thoughts.
</think>

First paragraph of answer.

Second paragraph of answer.`
      const result = parseThinking(input)
      expect(result.thinking).toContain('First paragraph of thinking')
      expect(result.thinking).toContain('Second paragraph')
      expect(result.thinking).toContain('Third paragraph')
      expect(result.answer).toContain('First paragraph of answer')
      expect(result.answer).toContain('Second paragraph of answer')
    })

    it('should handle </think> with no content after', () => {
      const input = '<think>thinking content</think>'
      const result = parseThinking(input)
      expect(result.thinking).toBe('thinking content')
      expect(result.answer).toBe('')
    })

    it('should handle nested tags in thinking content', () => {
      const input = '<think>Let me think about <div>HTML</div> tags</think>Answer with <span>tags</span>'
      const result = parseThinking(input)
      expect(result.thinking).toContain('<div>HTML</div>')
      expect(result.answer).toContain('<span>tags</span>')
    })
  })
})

// ──────────────────────────────────────────────────────────────
// Media display tests (TDD — these should FAIL until media rendering is added)
// ──────────────────────────────────────────────────────────────
import { render, screen } from '@testing-library/react'
import { ChatMessageList } from '../../components/chat/ChatMessageList'
import type { Message } from '../../stores/chat'

function makeMsg(overrides: Partial<Message> = {}): Message {
  return {
    id: 'msg-1',
    role: 'user',
    content: 'Hello',
    createdAt: new Date().toISOString(),
    ...overrides,
  }
}

describe('ChatMessageList — media display', () => {
  describe('user message attachments', () => {
    it('renders <img> for user message with image attachment', () => {
      const messages = [
        makeMsg({
          id: 'u1',
          role: 'user',
          content: 'Check this image',
          attachments: [
            { url: 'https://example.com/photo.jpg', type: 'image/jpeg', name: 'photo.jpg' },
          ],
        }),
      ]
      render(<ChatMessageList messages={messages} />)

      const img = screen.getByAltText('photo.jpg')
      expect(img).toBeInTheDocument()
      expect(img.tagName).toBe('IMG')
      expect(img).toHaveAttribute('src', 'https://example.com/photo.jpg')
    })

    it('renders <video> for user message with video attachment', () => {
      const messages = [
        makeMsg({
          id: 'u2',
          role: 'user',
          content: 'Watch this',
          attachments: [
            { url: 'https://example.com/clip.mp4', type: 'video/mp4', name: 'clip.mp4' },
          ],
        }),
      ]
      render(<ChatMessageList messages={messages} />)

      const videoEl = document.querySelector('video')
      expect(videoEl).toBeTruthy()
      expect(videoEl).toHaveAttribute('src', 'https://example.com/clip.mp4')
      expect(videoEl).toHaveAttribute('controls')
    })

    it('renders <audio> for user message with audio attachment', () => {
      const messages = [
        makeMsg({
          id: 'u3',
          role: 'user',
          content: 'Listen to this',
          attachments: [
            { url: 'https://example.com/song.mp3', type: 'audio/mpeg', name: 'song.mp3' },
          ],
        }),
      ]
      render(<ChatMessageList messages={messages} />)

      const audio = document.querySelector('audio')
      expect(audio).toBeTruthy()
      expect(audio).toHaveAttribute('src', 'https://example.com/song.mp3')
      expect(audio).toHaveAttribute('controls')
    })

    it('renders <a> link for user message with script attachment', () => {
      const messages = [
        makeMsg({
          id: 'u4',
          role: 'user',
          content: 'Here is my script',
          attachments: [
            { url: 'https://example.com/script.txt', kind: 'script', name: 'script.txt' },
          ],
        }),
      ]
      render(<ChatMessageList messages={messages} />)

      const link = screen.getByText('script.txt')
      expect(link).toBeInTheDocument()
      expect(link.tagName).toBe('A')
      expect(link).toHaveAttribute('href', 'https://example.com/script.txt')
      expect(link).toHaveAttribute('target', '_blank')
    })

    it('renders all elements for user message with multiple attachments', () => {
      const messages = [
        makeMsg({
          id: 'u5',
          role: 'user',
          content: 'Multiple files',
          attachments: [
            { url: 'https://example.com/img.png', type: 'image/png', name: 'img.png' },
            { url: 'https://example.com/vid.mp4', type: 'video/mp4', name: 'vid.mp4' },
            { url: 'https://example.com/doc.pdf', type: 'application/pdf', name: 'doc.pdf' },
          ],
        }),
      ]
      render(<ChatMessageList messages={messages} />)

      // Image should render
      expect(screen.getByAltText('img.png')).toBeInTheDocument()
      // Video should render
      expect(document.querySelector('video')).toBeTruthy()
      // Non-media should render as link
      expect(screen.getByText('doc.pdf')).toBeInTheDocument()
    })
  })

  describe('assistant message mediaResult', () => {
    it('renders <img> for assistant message with image mediaResult', () => {
      const messages = [
        makeMsg({
          id: 'a1',
          role: 'assistant',
          content: 'Here is your generated image',
          mediaResult: { kind: 'image', url: 'https://example.com/generated.png', mime_type: 'image/png' },
        }),
      ]
      render(<ChatMessageList messages={messages} />)

      const img = document.querySelector('img')
      expect(img).toBeTruthy()
      expect(img).toHaveAttribute('src', 'https://example.com/generated.png')
    })

    it('renders <video> for assistant message with video mediaResult', () => {
      const messages = [
        makeMsg({
          id: 'a2',
          role: 'assistant',
          content: 'Here is your generated video',
          mediaResult: { kind: 'video', url: 'https://example.com/generated.mp4', mime_type: 'video/mp4' },
        }),
      ]
      render(<ChatMessageList messages={messages} />)

      const video = document.querySelector('video')
      expect(video).toBeTruthy()
      expect(video).toHaveAttribute('src', 'https://example.com/generated.mp4')
      expect(video).toHaveAttribute('controls')
    })
  })

  describe('no media', () => {
    it('renders just text when message has no media', () => {
      const messages = [
        makeMsg({ id: 'plain1', role: 'user', content: 'Just a plain text message' }),
        makeMsg({ id: 'plain2', role: 'assistant', content: 'A plain response' }),
      ]
      render(<ChatMessageList messages={messages} />)

      expect(screen.getByText('Just a plain text message')).toBeInTheDocument()
      // Assistant content rendered via ReactMarkdown — check it exists in the DOM
      expect(screen.getByText('A plain response')).toBeInTheDocument()
      // No media elements should be present
      expect(document.querySelector('img')).toBeNull()
      expect(document.querySelector('video')).toBeNull()
      expect(document.querySelector('audio')).toBeNull()
    })
  })
})
