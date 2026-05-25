import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { Message } from '../../stores/chat'

interface ChatMessageListProps {
  messages: Message[]
  streaming?: boolean
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] rounded-lg bg-muted px-4 py-3 text-foreground">
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/40 [animation-delay:0ms]" />
          <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/40 [animation-delay:150ms]" />
          <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/40 [animation-delay:300ms]" />
        </div>
      </div>
    </div>
  )
}

/**
 * Parse a model response into { thinking, answer } parts.
 *
 * Supported formats:
 *   - DeepSeek / Ollama: <think>...</think>
 *   - Qwen: 【thinking】...【/thinking】
 *   - GLM / Poe inline: "Thinking...\n[analysis]\nGenerate Response...\n[answer]"
 */
function parseThinking(content: string): { thinking: string; answer: string } {
  // <think>...</think> (DeepSeek / Ollama format)
  const thinkMatch = content.match(/<think>([\s\S]*?)<\/think>/)
  if (thinkMatch) {
    const before = content.slice(0, thinkMatch.index)
    const after = content.slice(thinkMatch.index! + thinkMatch[0].length)
    return {
      thinking: (before + thinkMatch[1]).trim(),
      answer: after.trim(),
    }
  }

  // 【thinking】...【/thinking】 (Qwen format)
  const qwMatch = content.match(/【thinking】([\s\S]*?)【\/thinking】/)
  if (qwMatch) {
    const before = content.slice(0, qwMatch.index)
    const after = content.slice(qwMatch.index! + qwMatch[0].length)
    return {
      thinking: (before + qwMatch[1]).trim(),
      answer: after.trim(),
    }
  }

  // Inline thinking (GLM / Poe / OpenAI reasoning models)
  // Look for generation markers using plain string search (more reliable than regex)
  const inlineMarkers = [
    "Generate Response. (Proceed to output).",
    "Generate Response. (Proceed to output)",
    "Generate Response (Proceed to output)",
    "Generate Final Response.",
    "Generate Response.",
    "\nFinal Answer",
    "\nActual Answer",
  ]
  for (const marker of inlineMarkers) {
    const idx = content.indexOf(marker)
    if (idx > 20 && idx + marker.length < content.length * 0.95) {
      const thinking = content.slice(0, idx).trim()
      const answer = content.slice(idx + marker.length).trim()
      if (answer.length > 0) {
        return { thinking, answer }
      }
    }
  }

  return { thinking: '', answer: content }
}

function AssistantMessage({ content, streaming }: { content: string; streaming?: boolean }) {
  const { thinking, answer } = parseThinking(content)
  const [showThinking, setShowThinking] = useState(true) // open while streaming

  // Collapse thinking when streaming ends (unless it's a tagged format)
  const prevStreaming = useRef(streaming)
  useEffect(() => {
    if (prevStreaming.current && !streaming) {
      // Streaming just finished — collapse if this is inline (not tagged) thinking
      const hasExplicitTags = content.includes('<think>') || content.includes('</think>') ||
        content.includes('【thinking】')
      if (!hasExplicitTags && thinking.length > 0) {
        setShowThinking(false)
      }
    }
    prevStreaming.current = streaming
  }, [streaming, content, thinking])

  const hasThinking = thinking.length > 0

  return (
    <div className="text-sm space-y-2">
      {/* Thinking section */}
      {hasThinking && (
        <div className="rounded border border-border/50 overflow-hidden">
          <button
            onClick={() => setShowThinking(!showThinking)}
            className="flex w-full items-center gap-1.5 bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted transition-colors"
          >
            {showThinking ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
            <span>Thinking {streaming ? '(in progress...)' : ''}</span>
          </button>
          {showThinking && (
            <div className="px-3 py-2 text-xs text-muted-foreground/70 italic border-t border-border/30 max-h-60 overflow-y-auto">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {thinking}
              </ReactMarkdown>
            </div>
          )}
        </div>
      )}

      {/* Answer section */}
      {answer ? (
        <div className="px-1">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {answer}
          </ReactMarkdown>
        </div>
      ) : !hasThinking ? (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content}
        </ReactMarkdown>
      ) : null}

      {/* Pulsing dots when streaming and answer is still empty */}
      {streaming && !answer && content === '' && (
        <span className="inline-flex items-center gap-0.5">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:200ms]" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:400ms]" />
        </span>
      )}
    </div>
  )
}

export function ChatMessageList({ messages, streaming }: ChatMessageListProps) {
  const visibleMessages = messages.filter((msg) => msg.role !== 'tool' && msg.role !== 'system')

  const showTypingIndicator =
    streaming && (visibleMessages.length === 0 || (visibleMessages[visibleMessages.length - 1]?.role !== 'assistant'))

  if (visibleMessages.length === 0 && !streaming) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        No messages yet. Start the conversation!
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto space-y-4 p-4">
      {visibleMessages.map((msg) => {
        const isUser = msg.role === 'user'
        return (
          <div key={msg.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[80%] rounded-lg px-4 py-2 ${
                isUser
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-foreground'
              }`}
            >
              {isUser ? (
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
              ) : (
                <AssistantMessage content={msg.content} streaming={streaming} />
              )}
            </div>
          </div>
        )
      })}

      {showTypingIndicator && <TypingIndicator />}

      <ScrollAnchor streaming={streaming ?? false} />
    </div>
  )
}

function ScrollAnchor({ streaming }: { streaming: boolean }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: streaming ? 'smooth' : 'auto' })
  }, [streaming])

  return <div ref={ref} />
}
