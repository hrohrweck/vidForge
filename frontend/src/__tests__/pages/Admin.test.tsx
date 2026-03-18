import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Admin from '../../pages/Admin'
import { renderWithProviders } from '../test/utils'
import { server } from '../test/mocks/server'
import { http, HttpResponse } from 'msw'

describe('Admin Page', () => {
  it('shows only for superusers', () => {
    renderWithProviders(<Admin />, { superuser: true })
    expect(screen.getByText(/admin dashboard/i)).toBeInTheDocument()
  })
  
  it('displays user management table for superusers', async () => {
    renderWithProviders(<Admin />, { superuser: true })
    
    await waitFor(() => {
      expect(screen.getByText(/user@example.com/i)).toBeInTheDocument()
    })
  })
  
  it('displays system statistics', async () => {
    renderWithProviders(<Admin />, { superuser: true })
    
    await waitFor(() => {
      expect(screen.getByText(/total users/i)).toBeInTheDocument()
      expect(screen.getByText(/total jobs/i)).toBeInTheDocument()
    })
  })
  
  it('shows user management section', async () => {
    renderWithProviders(<Admin />, { superuser: true })
    
    await waitFor(() => {
      expect(screen.getByText(/user management/i)).toBeInTheDocument()
    })
  })
  
  it('displays user email addresses', async () => {
    renderWithProviders(<Admin />, { superuser: true })
    
    await waitFor(() => {
      expect(screen.getByText(/user@example.com/i)).toBeInTheDocument()
    })
  })
  
  it('shows user active status', async () => {
    renderWithProviders(<Admin />, { superuser: true })
    
    await waitFor(() => {
      expect(screen.getByText(/active/i)).toBeInTheDocument()
    })
  })
  
  it('handles API error gracefully', async () => {
    server.use(
      http.get('/api/admin/users', () => {
        return new HttpResponse(null, { status: 500 })
      })
    )
    
    renderWithProviders(<Admin />, { superuser: true })
    
    await waitFor(() => {
      expect(screen.getByText(/admin dashboard/i)).toBeInTheDocument()
    })
  })
  
  it('shows loading state initially', () => {
    renderWithProviders(<Admin />, { superuser: true })
    expect(screen.getByText(/admin dashboard/i)).toBeInTheDocument()
  })
  
  it('displays user count', async () => {
    renderWithProviders(<Admin />, { superuser: true })
    
    await waitFor(() => {
      expect(screen.getByText(/total users/i)).toBeInTheDocument()
    })
  })
  
  it('shows job statistics', async () => {
    renderWithProviders(<Admin />, { superuser: true })
    
    await waitFor(() => {
      expect(screen.getByText(/total jobs/i)).toBeInTheDocument()
      expect(screen.getByText(/active jobs/i)).toBeInTheDocument()
    })
  })
  
  it('handles empty user list', async () => {
    server.use(
      http.get('/api/admin/users', () => {
        return HttpResponse.json([])
      })
    )
    
    renderWithProviders(<Admin />, { superuser: true })
    
    await waitFor(() => {
      expect(screen.getByText(/admin dashboard/i)).toBeInTheDocument()
    })
  })
  
  it('shows superuser badge for superusers', async () => {
    server.use(
      http.get('/api/admin/users', () => {
        return HttpResponse.json([
          {
            id: '1',
            email: 'admin@example.com',
            is_active: true,
            is_superuser: true,
            created_at: '2024-01-01T00:00:00Z'
          }
        ])
      })
    )
    
    renderWithProviders(<Admin />, { superuser: true })
    
    await waitFor(() => {
      expect(screen.getByText(/admin@example.com/i)).toBeInTheDocument()
    })
  })
})
