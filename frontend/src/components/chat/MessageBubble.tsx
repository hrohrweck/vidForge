import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message } from '../../stores/chat'
import JobProgress from './JobProgress'
import { useChatStore } from '../../stores/chat'

interface MessageBubbleProps {
  message: Message
  conversationId?: string
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

export function MessageBubble({ message, conversationId }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div
      className={`mb-3 flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
    >
      <div
        className={`mb-1 flex items-baseline gap-2 text-[11px] text-muted-foreground ${
          isUser ? 'flex-row-reverse' : 'flex-row'
        }`}
      >
        <span className="font-medium text-foreground/80">
          {isUser ? 'You' : 'Assistant'}
        </span>
        <span title={new Date(message.createdAt).toLocaleString()}>
          {new Date(message.createdAt).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })}
          {' · '}
          {formatTime(message.createdAt)}
        </span>
      </div>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 ${
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted text-foreground'
        }`}
      >
        {message.attachments && message.attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {message.attachments.map((att, i) => {
              const kind = att.type ?? att.kind ?? att.mime_type
              const isImage = (att.type ?? att.mime_type ?? '').startsWith('image') || att.kind === 'image'
              const isVideo = (att.type ?? att.mime_type ?? '').startsWith('video') || att.kind === 'video'
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
                  {att.name || kind || 'Attachment'}
                </a>
              )
            })}
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
      {!isUser && message.jobId && !message.mediaResult && conversationId && (
        <JobProgress
          jobId={message.jobId}
          onComplete={(payload) => {
            const url = payload.output_path ?? payload.preview_path ?? ''
            const kind = /\.(mp4|webm|mov)$/i.test(url)
              ? 'video'
              : /\.(jpe?g|png|webp|gif)$/i.test(url)
                ? 'image'
                : 'media'
            useChatStore.getState().updateMessage(conversationId, message.id, {
              mediaResult: { kind, url },
            })
          }}
        />
      )}
    </div>
  )
}