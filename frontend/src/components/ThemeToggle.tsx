import { Sun, Moon, Monitor } from 'lucide-react'
import { useThemeStore, Theme } from '../stores/theme'
import { Button } from './ui/button'

const themeConfig: Record<Theme, { icon: typeof Sun; label: string; next: Theme }> = {
  light: { icon: Sun, label: 'Light mode', next: 'dark' },
  dark: { icon: Moon, label: 'Dark mode', next: 'system' },
  system: { icon: Monitor, label: 'System preference', next: 'light' },
}

export function ThemeToggle() {
  const { theme, cycleTheme } = useThemeStore()
  const config = themeConfig[theme]
  const Icon = config.icon

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={cycleTheme}
      title={`${config.label} (click to switch)`}
      className="h-9 w-9"
    >
      <Icon className="h-5 w-5" />
      <span className="sr-only">{config.label}</span>
    </Button>
  )
}
