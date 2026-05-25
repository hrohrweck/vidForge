import { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
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

export function ChatMessageList({ messages, streaming }: ChatMessageListProps) {
  const showTypingIndicator =
    streaming && (messages.length === 0 || (messages[messages.length - 1].role !== 'assistant'))

  if (messages.length === 0 && !streaming) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        No messages yet. Start the conversation!
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto space-y-4 p-4">
      {messages.map((msg) => {
        const isUser = msg.role === 'user'
        const isEmptyAssistant = !isUser && streaming && msg.content === ''
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
                <div className="text-sm">
                  {isEmptyAssistant ? (
                    <span className="inline-flex items-center gap-0.5">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:200ms]" />
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:400ms]" />
                    </span>
                  ) : (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  )}
                </div>
              )}
            </div>
          </div>
        )
      })}

      {/* Standalone typing indicator when no assistant message exists yet */}
      {showTypingIndicator && <TypingIndicator />}

      {/* Auto-scroll to bottom */}
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


