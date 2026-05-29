import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message } from '../../stores/chat'

interface MessageBubbleProps {
  message: Message
}

function formatTime(iso: string): string {
  const now = Date.now()
  const then = new Date(iso).getTime()
  const diff = now - then
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div
      className={`mb-3 flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
    >
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 ${
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted text-foreground'
        }`}
      >
        {message.attachments && message.attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {message.attachments.map((att, i) =>
              att.type?.startsWith('image') ? (
                <img
                  key={i}
                  src={att.url}
                  alt={att.name || 'attachment'}
                  className="max-w-[200px] max-h-[200px] rounded-lg object-cover cursor-pointer"
                  onClick={() => window.open(att.url, '_blank')}
                />
              ) : att.type?.startsWith('video') ? (
                <video
                  key={i}
                  src={att.url}
                  controls
                  className="max-w-[300px] max-h-[200px] rounded-lg"
                />
              ) : (
                <a
                  key={i}
                  href={att.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-primary hover:underline"
                >
                  {att.name || 'Attachment'}
                </a>
              )
            )}
          </div>
        )}
        {isUser ? (
          <p className="text-sm">{message.content}</p>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        )}
      </div>
      <span
        className={`mt-1 text-xs text-muted-foreground ${isUser ? 'text-right' : 'text-left'}`}
        title={new Date(message.createdAt).toLocaleString()}
      >
        {formatTime(message.createdAt)}
      </span>
    </div>
  )
}