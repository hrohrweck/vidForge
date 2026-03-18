import { Outlet, NavLink } from 'react-router-dom'
import { Video, FileVideo, Settings, LogOut, Clapperboard, Shield } from 'lucide-react'
import { useAuthStore } from '../stores/auth'
import { cn } from '../lib/utils'

const getNavItems = (isSuperuser: boolean) => [
  { to: '/', label: 'Dashboard', icon: Video },
  { to: '/jobs', label: 'Jobs', icon: Clapperboard },
  { to: '/templates', label: 'Templates', icon: FileVideo },
  { to: '/settings', label: 'Settings', icon: Settings },
  ...(isSuperuser ? [{ to: '/admin', label: 'Admin', icon: Shield }] : []),
]

export default function Layout() {
  const { user, logout } = useAuthStore()
  const navItems = getNavItems(user?.is_superuser || false)

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Video className="h-6 w-6" />
            <span className="font-bold text-lg">VidForge</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted-foreground">{user?.email}</span>
            <button
              onClick={logout}
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
            >
              <LogOut className="h-4 w-4" />
              Logout
            </button>
          </div>
        </div>
      </header>
      <div className="container mx-auto px-4 py-6 flex gap-6">
        <nav className="w-48 shrink-0">
          <ul className="space-y-1">
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors',
                      isActive
                        ? 'bg-secondary text-secondary-foreground'
                        : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                    )
                  }
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <main className="flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
