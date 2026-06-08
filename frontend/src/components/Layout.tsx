import { useState } from 'react'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import {
  Video,
  FileVideo,
  Settings,
  LogOut,
  Clapperboard,
  Shield,
  Users,
  Server,
  Image,
  Menu,
  ChevronLeft,
  ChevronRight,
  User as UserIcon,
  MessageSquare,
  ScrollText,
} from 'lucide-react'
import { useAuthStore } from '../stores/auth'
import { ThemeToggle } from './ThemeToggle'
import { cn } from '../lib/utils'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu'
import { Avatar, AvatarFallback } from './ui/avatar'
import { Button } from './ui/button'

interface NavItem {
  to: string
  label: string
  icon: React.ComponentType<{ className?: string }>
}

interface NavGroup {
  label: string
  icon: React.ComponentType<{ className?: string }>
  children: NavItem[]
}

type NavEntry = NavItem | NavGroup

function isGroup(entry: NavEntry): entry is NavGroup {
  return 'children' in entry
}

const getNavEntries = (isSuperuser: boolean): NavEntry[] => [
  { to: '/', label: 'Dashboard', icon: Video },
  { to: '/jobs', label: 'Jobs', icon: Clapperboard },
  { to: '/templates', label: 'Templates', icon: FileVideo },
  { to: '/media', label: 'Media Library', icon: Image },
  { to: '/avatars', label: 'Avatars', icon: UserIcon },
  { to: '/chat', label: 'Chat', icon: MessageSquare },
  { to: '/settings', label: 'Settings', icon: Settings },
  ...(isSuperuser
    ? [
        {
          label: 'Admin',
          icon: Shield,
          children: [
            { to: '/admin', label: 'Overview', icon: Users },
            { to: '/admin/providers', label: 'Providers', icon: Server },
            { to: '/admin/models', label: 'Models', icon: Server },
            { to: '/admin/groups', label: 'Groups', icon: Users },
            { to: '/admin/logs', label: 'Logs', icon: ScrollText },
          ],
        } as NavGroup,
      ]
    : []),
]

export default function Layout() {
  const { user, logout } = useAuthStore()
  const location = useLocation()
  const isChatPage = location.pathname === '/chat'
  const isFullPage = isChatPage || location.pathname === '/media' || location.pathname.startsWith('/media/') || location.pathname.startsWith('/editor/') || location.pathname === '/settings' || location.pathname === '/jobs'
  const navEntries = getNavEntries(user?.is_superuser || false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

  const closeMobileMenu = () => setIsMobileMenuOpen(false)

  // Track which groups are expanded — keyed by group label
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({})

  const toggleGroup = (label: string) => {
    setExpandedGroups((prev) => ({ ...prev, [label]: !prev[label] }))
  }

  const isGroupActive = (group: NavGroup) =>
    group.children.some((child) => location.pathname === child.to || location.pathname.startsWith(child.to + '/'))

  return (
    <div className="h-screen overflow-hidden bg-background flex flex-col">
      <header className="sticky top-0 z-50 w-full border-b border-border backdrop-blur-md bg-header-bg/80">
        <div className="h-14 flex items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="md:hidden"
            >
              <Menu className="h-5 w-5" />
            </Button>
            <div className="flex items-center gap-2">
              <Video className="h-6 w-6 text-primary" />
              <span className="font-bold text-lg tracking-tight">VidForge</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="relative h-8 w-8 rounded-full">
                  <Avatar className="h-8 w-8">
                    <AvatarFallback className="bg-primary/10 text-primary">
                      {user?.email?.charAt(0).toUpperCase() || <UserIcon className="h-4 w-4" />}
                    </AvatarFallback>
                  </Avatar>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-56" align="end" forceMount>
                <DropdownMenuLabel className="font-normal">
                  <div className="flex flex-col space-y-1">
                    <p className="text-sm font-medium leading-none">Account</p>
                    <p className="text-xs leading-none text-muted-foreground">
                      {user?.email}
                    </p>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout} className="text-destructive focus:text-destructive cursor-pointer">
                  <LogOut className="mr-2 h-4 w-4" />
                  <span>Log out</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {isMobileMenuOpen && (
          <div
            className="fixed inset-0 z-35 bg-black/50 transition-opacity md:hidden"
            onClick={closeMobileMenu}
          />
        )}
        <aside
          className={cn(
            "fixed inset-y-0 left-0 z-40 flex flex-col border-r border-sidebar-border bg-sidebar-bg transition-all duration-300 ease-in-out md:relative md:translate-x-0",
            isMobileMenuOpen ? "w-64 translate-x-0" : "-translate-x-full md:translate-x-0",
            isSidebarOpen ? "md:w-64" : "md:w-16"
          )}
        >
          <div className="flex items-center justify-end p-2 md:hidden">
            <Button variant="ghost" size="icon" onClick={closeMobileMenu}>
              <ChevronLeft className="h-5 w-5" />
            </Button>
          </div>
          <nav className="flex-1 overflow-y-auto py-4">
            <ul className="space-y-1 px-2">
              {navEntries.map((entry) =>
                isGroup(entry) ? (
                  /* ── Collapsible group ─────────────────────────── */
                  <NavGroupItem
                    key={entry.label}
                    group={entry}
                    expanded={expandedGroups[entry.label] ?? isGroupActive(entry)}
                    active={isGroupActive(entry)}
                    collapsed={!isSidebarOpen}
                    onToggle={() => toggleGroup(entry.label)}
                    onNavClick={closeMobileMenu}
                  />
                ) : (
                  /* ── Flat link ─────────────────────────────────── */
                  <li key={entry.to}>
                    <NavLink
                      to={entry.to}
                      end={entry.to === '/'}
                      onClick={closeMobileMenu}
                      className={({ isActive }) =>
                        cn(
                          'group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all',
                          isActive
                            ? 'bg-primary/10 text-primary'
                            : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
                          !isSidebarOpen && 'md:justify-center md:px-0'
                        )
                      }
                      title={!isSidebarOpen ? entry.label : undefined}
                    >
                      {({ isActive }) => (
                        <>
                          <div className={cn(
                            "absolute left-0 h-8 w-1 rounded-r-full bg-primary transition-all",
                            isActive ? "opacity-100" : "opacity-0"
                          )} />
                          <entry.icon className={cn("h-5 w-5 shrink-0", isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} />
                          <span className={cn(
                            "transition-all duration-300",
                            !isSidebarOpen && "md:hidden"
                          )}>
                            {entry.label}
                          </span>
                        </>
                      )}
                    </NavLink>
                  </li>
                )
              )}
            </ul>
          </nav>

          <div className="p-4 border-t border-sidebar-border hidden md:flex justify-center">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="text-muted-foreground hover:text-foreground"
            >
              <ChevronLeft className={cn("h-5 w-5 transition-transform duration-300", !isSidebarOpen && "rotate-180")} />
            </Button>
          </div>
        </aside>

        <main className="flex-1 min-h-0 overflow-hidden bg-background/50">
          <div className={isFullPage ? 'h-full w-full p-0' : 'container mx-auto p-6 max-w-6xl'}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}

/* ── Collapsible nav group component ─────────────────────────────── */

interface NavGroupItemProps {
  group: NavGroup
  expanded: boolean
  active: boolean
  collapsed: boolean
  onToggle: () => void
  onNavClick: () => void
}

function NavGroupItem({ group, expanded, active, collapsed, onToggle, onNavClick }: NavGroupItemProps) {
  return (
    <li>
      {/* Group header — clickable to expand/collapse */}
      <button
        onClick={onToggle}
        className={cn(
          'group flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all',
          active
            ? 'bg-primary/5 text-foreground'
            : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
          collapsed && 'md:justify-center md:px-0'
        )}
        title={collapsed ? group.label : undefined}
      >
        <group.icon className={cn("h-5 w-5 shrink-0", active ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} />
        <span className={cn(
          "flex-1 text-left transition-all duration-300",
          collapsed && "md:hidden"
        )}>
          {group.label}
        </span>
        {!collapsed && (
          <ChevronRight className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
            expanded && "rotate-90"
          )} />
        )}
      </button>

      {/* Sub-items */}
      <div className={cn(
        "overflow-hidden transition-all duration-200",
        expanded ? "max-h-40 opacity-100" : "max-h-0 opacity-0"
      )}>
        <ul className="mt-1 space-y-0.5 pl-3 border-l-2 border-border ml-2.5">
          {group.children.map((child) => (
            <li key={child.to}>
              <NavLink
                to={child.to}
                end={child.to === '/admin'}
                onClick={onNavClick}
                className={({ isActive }) =>
                  cn(
                    'group flex items-center gap-3 rounded-md px-3 py-1.5 text-sm transition-all',
                    isActive
                      ? 'bg-primary/10 text-primary font-medium'
                      : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
                    collapsed && 'md:hidden'
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <child.icon className={cn("h-4 w-4 shrink-0", isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} />
                    <span className="text-[0.8125rem]">{child.label}</span>
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>
    </li>
  )
}
