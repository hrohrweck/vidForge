import { render, RenderOptions } from '@testing-library/react'
import { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
})

interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  authenticated?: boolean
  superuser?: boolean
}

export function renderWithProviders(
  ui: ReactElement,
  options?: CustomRenderOptions
) {
  const { authenticated = true, superuser = false, ...renderOptions } = options || {}
  
  if (authenticated) {
    useAuthStore.setState({
      token: superuser ? 'superuser-token' : 'test-token',
      user: {
        id: '1',
        email: superuser ? 'admin@example.com' : 'test@example.com',
        is_active: true,
        is_superuser: superuser,
        groups: [],
        permissions: [],
      },
      isAuthenticated: true,
    })
  } else {
    useAuthStore.setState({
      token: null,
      user: null
    })
  }
  
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {ui}
      </BrowserRouter>
    </QueryClientProvider>,
    renderOptions
  )
}

export function createMockFile(content: string, name: string, type: string): File {
  return new File([content], name, { type })
}
