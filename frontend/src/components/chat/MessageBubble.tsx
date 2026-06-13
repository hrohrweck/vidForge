import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { Message, JobCardAttachment } from '../../stores/chat'
import JobProgress from './JobProgress'
import { useChatStore } from '../../stores/chat'
import {
  JobDraftCard,
  ScenePlanCard,
  ImageReviewCard,
  VideoReviewCard,
  JobCompletedCard,
  JobErrorCard,
} from './cards'

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

function parseThinking(content: string): { thinking: string; answer: string } {
  // <think>...</think> (DeepSeek / Ollama / instructed format)
  const thinkMatch = content.match(/<think>([\s\S]*?)<\/think>/)
  if (thinkMatch) {
    const before = content.slice(0, thinkMatch.index).trim()
    const after = content.slice(thinkMatch.index! + thinkMatch[0].length).trim()
    const thinking = [before, thinkMatch[1]].filter(Boolean).join('\n').trim()
    return { thinking, answer: after }
  }

  // Qwen / CJK thinking markers
  const cjkMatch = content.match(/【thinking】([\s\S]*?)【\/thinking】/)
  if (cjkMatch) {
    const before = content.slice(0, cjkMatch.index).trim()
    const after = content.slice(cjkMatch.index! + cjkMatch[0].length).trim()
    const thinking = [before, cjkMatch[1]].filter(Boolean).join('\n').trim()
    return { thinking, answer: after }
  }

  // Streaming partial: hide everything from an unclosed <think> tag
  const openIdx = content.indexOf('<think>')
  if (openIdx !== -1) {
    return {
      thinking: content.slice(openIdx + 7).trim(),
      answer: content.slice(0, openIdx).trim(),
    }
  }

  // Common inline reasoning markers
  const markers = [
    'Generate Response. (Proceed to output)',
    'Generate Response (Proceed to output)',
    'Generate Final Response.',
    'Generate Response.',
    '\nFinal Answer',
    '\nActual Answer',
    '\nAnswer:',
  ]
  for (const marker of markers) {
    const idx = content.indexOf(marker)
    if (idx > 20 && idx + marker.length < content.length * 0.95) {
      return {
        thinking: content.slice(0, idx).trim(),
        answer: content.slice(idx + marker.length).trim(),
      }
    }
  }

  return { thinking: '', answer: content }
}

function AssistantContent({ content }: { content: string }) {
  const { thinking, answer } = parseThinking(content)
  const [showThinking, setShowThinking] = useState(false)
  const hasThinking = thinking.length > 0

  return (
    <div className="text-sm space-y-2">
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
            <span>Thinking</span>
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
      {answer ? (
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {answer}
          </ReactMarkdown>
        </div>
      ) : !hasThinking ? (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content}
        </ReactMarkdown>
      ) : null}
    </div>
  )
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
              if (att.kind === 'job_card') {
                const card = att as JobCardAttachment
                const cardComponent = {
                  job_draft: <JobDraftCard data={card.data} jobId={card.job_id} conversationId={conversationId} messageId={message.id} />,
                  scene_plan: <ScenePlanCard data={card.data} jobId={card.job_id} />,
                  image_review: <ImageReviewCard data={card.data} jobId={card.job_id} />,
                  video_review: <VideoReviewCard data={card.data} jobId={card.job_id} />,
                  job_completed: <JobCompletedCard data={card.data} jobId={card.job_id} />,
                  job_error: <JobErrorCard data={card.data} jobId={card.job_id} />,
                }[card.card_type]

                return (
                  <div key={i} className="w-full">
                    {cardComponent ?? (
                      <div className="rounded border bg-muted p-2 text-xs text-muted-foreground">
                        Unknown card type: {card.card_type}
                      </div>
                    )}
                  </div>
                )
              }

              const legacyAtt = att as {url: string; type?: string; name?: string; kind?: string; mime_type?: string}
              const kind = legacyAtt.type ?? legacyAtt.kind ?? legacyAtt.mime_type
              const isImage = (legacyAtt.type ?? legacyAtt.mime_type ?? '').startsWith('image') || legacyAtt.kind === 'image'
              const isVideo = (legacyAtt.type ?? legacyAtt.mime_type ?? '').startsWith('video') || legacyAtt.kind === 'video'
              return isImage ? (
                <img
                  key={i}
                  src={legacyAtt.url}
                  alt={legacyAtt.name || 'attachment'}
                  className="max-w-[200px] max-h-[200px] rounded-lg object-cover cursor-pointer"
                  onClick={() => window.open(legacyAtt.url, '_blank')}
                />
              ) : isVideo ? (
                <video
                  key={i}
                  src={legacyAtt.url}
                  controls
                  className="max-w-[300px] max-h-[200px] rounded-lg"
                />
              ) : (
                <a
                  key={i}
                  href={legacyAtt.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-primary hover:underline"
                >
                  {legacyAtt.name || kind || 'Attachment'}
                </a>
              )
            })}
          </div>
        )}
        {isUser ? (
          <p className="text-sm">{message.content}</p>
        ) : (
          <AssistantContent content={message.content} />
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