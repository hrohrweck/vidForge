import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Layout from '../../../src/components/Layout'
import { useAuthStore } from '../../../src/stores/auth'
import { useUiStore } from '../../../src/stores/ui'
import { usersApi } from '../../../src/api/client'

vi.mock('../../../src/api/client', () => ({
  usersApi: {
    setSidebarPreference: vi.fn().mockResolvedValue({}),
    getSidebarPreference: vi.fn().mockResolvedValue({ sidebar_open: true }),
  },
  authApi: {
    getMe: vi.fn().mockResolvedValue({ data: {} }),
  }
}))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
})

function renderLayout() {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<div>Dashboard Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('Layout Sidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({
      user: {
        id: '1',
        email: 'test@example.com',
        is_active: true,
        is_superuser: false,
        groups: [],
        permissions: [],
      },
      isAuthenticated: true,
    })
    useUiStore.setState({
      isSidebarOpen: true,
      sidebarHydrated: false,
      sidebarError: null,
    })
  })

  it('default state renders collapse button and expanded labels', () => {
    renderLayout()
    
    const collapseButton = screen.getByLabelText('Collapse sidebar')
    expect(collapseButton).toBeInTheDocument()
    
    const dashboardLabel = screen.getByText('Dashboard')
    expect(dashboardLabel).toBeInTheDocument()
    expect(dashboardLabel.className).not.toContain('md:hidden')
  })

  it('clicking collapse calls usersApi.setSidebarPreference(false) and shows expand button', async () => {
    renderLayout()
    
    const collapseButton = screen.getByLabelText('Collapse sidebar')
    fireEvent.click(collapseButton)
    
    expect(usersApi.setSidebarPreference).toHaveBeenCalledWith(false)
    
    const expandButton = await screen.findByLabelText('Expand sidebar')
    expect(expandButton).toBeInTheDocument()
    
    const dashboardLabel = screen.getByText('Dashboard')
    expect(dashboardLabel.className).toContain('md:hidden')
  })

  it('mocked hydrated collapsed state renders expand button without local default overriding it', () => {
    useUiStore.setState({
      isSidebarOpen: false,
      sidebarHydrated: true,
    })
    
    renderLayout()
    
    const expandButton = screen.getByLabelText('Expand sidebar')
    expect(expandButton).toBeInTheDocument()
    
    const dashboardLabel = screen.getByText('Dashboard')
    expect(dashboardLabel.className).toContain('md:hidden')
  })
})

describe('Layout Sidebar Submenu (collapsed desktop)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({
      user: {
        id: '1',
        email: 'admin@example.com',
        is_active: true,
        is_superuser: true,
        groups: [],
        permissions: [],
      },
      isAuthenticated: true,
    })
    useUiStore.setState({
      isSidebarOpen: false,
      sidebarHydrated: true,
      sidebarError: null,
    })
  })

  it('clicking a group in the collapsed sidebar opens a submenu view with Back', () => {
    renderLayout()

    const adminButton = screen.getByTitle('Admin')
    fireEvent.click(adminButton)

    expect(screen.getByText('Back')).toBeInTheDocument()
    expect(screen.getByText('Overview')).toBeInTheDocument()
    expect(screen.getByText('Providers')).toBeInTheDocument()
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument()
  })

  it('clicking Back restores the collapsed main menu without saving sidebar preference', () => {
    renderLayout()

    fireEvent.click(screen.getByTitle('Admin'))
    fireEvent.click(screen.getByText('Back'))

    expect(screen.queryByText('Back')).not.toBeInTheDocument()
    expect(screen.queryByText('Overview')).not.toBeInTheDocument()
    expect(screen.getByText('Dashboard')).toBeInTheDocument()

    expect(usersApi.setSidebarPreference).not.toHaveBeenCalled()
  })

  it('expanded sidebar keeps existing inline group expansion', () => {
    useUiStore.setState({ isSidebarOpen: true, sidebarHydrated: true })
    renderLayout()

    const adminButton = screen.getByText('Admin')
    fireEvent.click(adminButton)

    expect(screen.getByText('Overview')).toBeInTheDocument()
    expect(screen.queryByText('Back')).not.toBeInTheDocument()
  })
})
