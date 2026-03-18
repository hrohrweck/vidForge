import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Jobs from '../../pages/Jobs'
import { renderWithProviders } from '../test/utils'
import { server } from '../test/mocks/server'
import { http, HttpResponse } from 'msw'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

describe('Jobs Page', () => {
  beforeEach(() => {
    mockNavigate.mockClear()
  })

  it('displays job list', async () => {
    renderWithProviders(<Jobs />)
    
    await waitFor(() => {
      expect(screen.getByText(/completed/i)).toBeInTheDocument()
    })
  })
  
  it('filters jobs by status', async () => {
    renderWithProviders(<Jobs />)
    
    await waitFor(() => {
      expect(screen.getByText('All')).toBeInTheDocument()
    })
    
    fireEvent.click(screen.getByText('Pending'))
    
    await waitFor(() => {
      expect(screen.getByText('Pending')).toBeInTheDocument()
    })
  })
  
  it('shows thumbnails for completed jobs', async () => {
    renderWithProviders(<Jobs />)
    
    await waitFor(() => {
      const thumbnail = screen.getByAltText(/job thumbnail/i)
      expect(thumbnail).toBeInTheDocument()
      expect(thumbnail).toHaveAttribute('src', '/api/uploads/uploads/thumb1.jpg')
    })
  })
  
  it('opens batch job modal', async () => {
    renderWithProviders(<Jobs />)
    
    await waitFor(() => {
      expect(screen.getByText(/batch create/i)).toBeInTheDocument()
    })
    
    fireEvent.click(screen.getByText(/batch create/i))
    
    await waitFor(() => {
      expect(screen.getByText(/create batch jobs/i)).toBeInTheDocument()
    })
  })
  
  it('opens job creation modal', async () => {
    renderWithProviders(<Jobs />)
    
    await waitFor(() => {
      expect(screen.getByText(/new job/i)).toBeInTheDocument()
    })
    
    fireEvent.click(screen.getByText(/new job/i))
    
    await waitFor(() => {
      expect(screen.getByText(/new job/i)).toBeInTheDocument()
    })
  })
  
  it('deletes job on button click', async () => {
    renderWithProviders(<Jobs />)
    
    await waitFor(() => {
      const deleteButtons = screen.getAllByRole('button', { name: /trash/i })
      expect(deleteButtons.length).toBeGreaterThan(0)
    })
  })
  
  it('navigates to job detail on click', async () => {
    renderWithProviders(<Jobs />)
    
    await waitFor(() => {
      const jobElement = screen.getByText(/completed/i)
      fireEvent.click(jobElement)
    })
    
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalled()
    })
  })
  
  it('shows empty state when no jobs', async () => {
    server.use(
      http.get('/api/jobs', () => {
        return HttpResponse.json([])
      })
    )
    
    renderWithProviders(<Jobs />)
    
    await waitFor(() => {
      expect(screen.getByText(/no jobs found/i)).toBeInTheDocument()
    })
  })
  
  it('displays job creation date', async () => {
    renderWithProviders(<Jobs />)
    
    await waitFor(() => {
      expect(screen.getByText(/completed/i)).toBeInTheDocument()
    })
  })
  
  it('shows progress for processing jobs', async () => {
    server.use(
      http.get('/api/jobs', () => {
        return HttpResponse.json([
          {
            id: '2',
            status: 'processing',
            progress: 75,
            input_data: { prompt: 'test' },
            output_path: null,
            preview_path: null,
            thumbnail_path: null,
            error_message: null,
            created_at: '2024-01-01T00:00:00Z',
            started_at: '2024-01-01T00:01:00Z',
            completed_at: null
          }
        ])
      })
    )
    
    renderWithProviders(<Jobs />)
    
    await waitFor(() => {
      expect(screen.getByText(/75%/i)).toBeInTheDocument()
    })
  })
})
