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
export function parseThinking(content: string): { thinking: string; answer: string } {
  // <think>...</think> (DeepSeek / Ollama format)
  const thinkMatch = content.match(/<think>([\s\S]*?)<\/think>/)
  if (thinkMatch) {
    // Detect per-token think blocks (3+ tags = many small blocks)
    const thinkTagCount = (content.match(/<think>/g) || []).length
    if (thinkTagCount >= 3) {
      // Many think blocks — extract entire region between first <think> and last </think>
      const firstThink = content.indexOf('<think>')
      const lastClose = content.lastIndexOf('</think>')
      const thinking = content.slice(firstThink + 7, lastClose).replace(/<\/?think>/g, '').trim()
      const answer = content.slice(lastClose + 8).trim()
      return { thinking, answer }
    }
    
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

  // Inline thinking (GLM / Poe / OpenAI / Claude reasoning models)
  // Handles: "Thinking\n[plain text]\n\n[answer]" and blockquoted reasoning
  if (content.startsWith('Thinking')) {
    const lines = content.split('\n')
    let splitIdx = 0
    let inReasoning = false
    for (let i = 1; i < lines.length; i++) {
      const line = lines[i]
      // Stop at <think> tags — those are handled by the tag parser
      if (line.includes('<think>') || line.includes('</think>')) {
        splitIdx = i
        break
      }
      if (line.startsWith('>') || line.trim() === '') {
        inReasoning = true
        splitIdx = i + 1
      } else if (inReasoning && line.trim().length > 0) {
        // First non-empty, non-blockquote line after reasoning = answer start
        splitIdx = i
        break
      }
    }
    if (splitIdx > 0 && splitIdx < lines.length) {
      // If the split line is a known answer marker, include it in thinking
      const splitLine = lines[splitIdx].trim()
      const answerMarkerPatterns = [
        /^Generate\s+(?:Final\s+)?Response/i,
        /^Final\s+Answer/i,
        /^Actual\s+Answer/i,
        /^Answer:/i,
      ]
      if (answerMarkerPatterns.some(re => re.test(splitLine))) {
        splitIdx++
      }
      const thinking = lines.slice(0, splitIdx).join('\n').trim()
      const answer = lines.slice(splitIdx).join('\n').trim()
      if (thinking.length > 10 && answer.length > 0) {
        return { thinking, answer }
      }
    }
    // If no clear split found, treat entire content after header as thinking
    // (the <think> tag parser above will further refine)
  }

  // Look for generation markers using plain string search
  const inlineMarkers = [
    "Generate Response. (Proceed to output).",
    "Generate Response. (Proceed to output)",
    "Generate Response (Proceed to output)",
    "Generate Final Response.",
    "Generate Response.",
    "\nFinal Answer",
    "\nActual Answer",
    "\nAnswer:",
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
  const [showThinking, setShowThinking] = useState(streaming ?? false) // open while streaming, collapsed for old chats

  // Collapse thinking when streaming ends (all formats)
  const prevStreaming = useRef(streaming)
  useEffect(() => {
    if (prevStreaming.current && !streaming && thinking.length > 0) {
      // Streaming just finished — collapse thinking
      setShowThinking(false)
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
          <div
            key={msg.id}
            className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`mb-1 flex items-baseline gap-2 text-[11px] text-muted-foreground ${
                isUser ? 'flex-row-reverse' : 'flex-row'
              }`}
            >
              <span className="font-medium text-foreground/80">
                {isUser ? 'You' : 'Assistant'}
              </span>
              <span title={new Date(msg.createdAt).toLocaleString()}>
                {new Date(msg.createdAt).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            </div>
            <div
              className={`max-w-[80%] rounded-lg px-4 py-2 ${
                isUser
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-foreground'
              }`}
            >
              {isUser ? (
                <>
                  {msg.attachments && msg.attachments.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-2">
                      {msg.attachments.map((att, i) => {
                        const isImage = (att.type ?? att.mime_type ?? '').startsWith('image') || att.kind === 'image'
                        const isVideo = (att.type ?? att.mime_type ?? '').startsWith('video') || att.kind === 'video'
                        const isAudio = (att.type ?? att.mime_type ?? '').startsWith('audio') || att.kind === 'audio'
                        return isImage ? (
                          <img
                            key={i}
                            src={att.url}
                            alt={att.name || 'attachment'}
                            className="max-w-[200px] max-h-[200px] rounded-lg object-cover cursor-pointer"
                            onClick={() => window.open(att.url, '_blank')}
                          />
                        ) : isVideo ? (
                          <video
                            key={i}
                            src={att.url}
                            controls
                            className="max-w-[200px] max-h-[200px] rounded-lg"
                          />
                        ) : isAudio ? (
                          <audio
                            key={i}
                            src={att.url}
                            controls
                            className="w-full"
                          />
                        ) : (
                          <a
                            key={i}
                            href={att.url}
                            target="_blank"
                            rel="noreferrer"
                            download
                            className="text-sm underline"
                          >
                            {att.name || (att.type ?? att.kind ?? att.mime_type) || 'Attachment'}
                          </a>
                        )
                      })}
                    </div>
                  )}
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                </>
              ) : (
                <>
                  <AssistantMessage content={msg.content} streaming={streaming} />
                  {msg.mediaResult && (
                    <div className="mt-2">
                      {msg.mediaResult.kind === 'image' ? (
                        <img
                          src={msg.mediaResult.url}
                          alt="Generated"
                          className="max-w-[300px] max-h-[300px] rounded-lg object-cover cursor-pointer"
                          onClick={() => window.open(msg.mediaResult?.url, '_blank')}
                        />
                      ) : msg.mediaResult.kind === 'video' ? (
                        <video
                          src={msg.mediaResult.url}
                          controls
                          className="max-w-[300px] max-h-[300px] rounded-lg"
                        />
                      ) : (
                        <a
                          href={msg.mediaResult.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary underline text-sm"
                        >
                          View media
                        </a>
                      )}
                    </div>
                  )}
                </>
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
