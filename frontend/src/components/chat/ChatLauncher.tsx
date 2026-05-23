import { MessageSquare } from 'lucide-react'
import { useAuthStore } from '../../stores/auth'
import { useChatStore } from '../../stores/chat'

export function ChatLauncher() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const togglePanel = useChatStore((s) => s.togglePanel)

  if (!isAuthenticated) return null

  return (
    <button
      onClick={togglePanel}
      className="fixed bottom-4 right-4 z-40 h-12 w-12 rounded-full bg-primary text-primary-foreground shadow-lg"
      aria-label="Open chat"
    >
      <MessageSquare className="mx-auto h-5 w-5" />
    </button>
  )
}