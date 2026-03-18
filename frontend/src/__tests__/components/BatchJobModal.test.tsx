import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BatchJobModal } from '../../components/BatchJobModal'
import { renderWithProviders } from '../test/utils'
import { server } from '../test/mocks/server'
import { http, HttpResponse } from 'msw'

describe('BatchJobModal', () => {
  it('renders modal when open', () => {
    renderWithProviders(<BatchJobModal isOpen={true} onClose={vi.fn()} />)
    expect(screen.getByText('Create Batch Jobs')).toBeInTheDocument()
  })
  
  it('does not render when closed', () => {
    renderWithProviders(<BatchJobModal isOpen={false} onClose={vi.fn()} />)
    expect(screen.queryByText('Create Batch Jobs')).not.toBeInTheDocument()
  })
  
  it('switches between manual and CSV mode', async () => {
    renderWithProviders(<BatchJobModal isOpen={true} onClose={vi.fn()} />)
    
    expect(screen.getByLabelText(/job inputs/i)).toBeInTheDocument()
    
    fireEvent.click(screen.getByText('Upload CSV'))
    expect(screen.getByLabelText(/csv file/i)).toBeInTheDocument()
    
    fireEvent.click(screen.getByText('Manual Input'))
    expect(screen.getByLabelText(/job inputs/i)).toBeInTheDocument()
  })
  
  it('validates JSON input in manual mode', async () => {
    const onClose = vi.fn()
    renderWithProviders(<BatchJobModal isOpen={true} onClose={onClose} />)
    
    const select = screen.getByLabelText(/template/i)
    fireEvent.change(select, { target: { value: '1' } })
    
    const textarea = screen.getByLabelText(/job inputs/i)
    await userEvent.type(textarea, 'invalid json')
    
    fireEvent.click(screen.getByText('Create Jobs'))
    
    await waitFor(() => {
      expect(screen.getByText(/invalid json/i)).toBeInTheDocument()
    })
    expect(onClose).not.toHaveBeenCalled()
  })
  
  it('submits batch job from valid JSON', async () => {
    const onClose = vi.fn()
    renderWithProviders(<BatchJobModal isOpen={true} onClose={onClose} />)
    
    const select = screen.getByLabelText(/template/i)
    fireEvent.change(select, { target: { value: '1' } })
    
    const textarea = screen.getByLabelText(/job inputs/i)
    await userEvent.clear(textarea)
    await userEvent.type(textarea, '[{"prompt": "test1"}, {"prompt": "test2"}]')
    
    fireEvent.click(screen.getByText('Create Jobs'))
    
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled()
    })
  })
  
  it('requires template selection', async () => {
    const onClose = vi.fn()
    renderWithProviders(<BatchJobModal isOpen={true} onClose={onClose} />)
    
    const textarea = screen.getByLabelText(/job inputs/i)
    await userEvent.type(textarea, '[{"prompt": "test"}]')
    
    fireEvent.click(screen.getByText('Create Jobs'))
    
    await waitFor(() => {
      expect(onClose).not.toHaveBeenCalled()
    })
  })
  
  it('requires CSV file in CSV mode', async () => {
    const onClose = vi.fn()
    renderWithProviders(<BatchJobModal isOpen={true} onClose={onClose} />)
    
    fireEvent.click(screen.getByText('Upload CSV'))
    
    const select = screen.getByLabelText(/template/i)
    fireEvent.change(select, { target: { value: '1' } })
    
    fireEvent.click(screen.getByText('Create Jobs'))
    
    await waitFor(() => {
      expect(screen.getByText(/select a csv file/i)).toBeInTheDocument()
    })
    expect(onClose).not.toHaveBeenCalled()
  })
  
  it('handles API error gracefully', async () => {
    server.use(
      http.post('/api/jobs/batch', () => {
        return new HttpResponse(null, { status: 500 })
      })
    )
    
    const onClose = vi.fn()
    renderWithProviders(<BatchJobModal isOpen={true} onClose={onClose} />)
    
    const select = screen.getByLabelText(/template/i)
    fireEvent.change(select, { target: { value: '1' } })
    
    const textarea = screen.getByLabelText(/job inputs/i)
    await userEvent.clear(textarea)
    await userEvent.type(textarea, '[{"prompt": "test"}]')
    
    fireEvent.click(screen.getByText('Create Jobs'))
    
    await waitFor(() => {
      expect(screen.getByText(/error creating jobs/i)).toBeInTheDocument()
    })
    expect(onClose).not.toHaveBeenCalled()
  })
  
  it('toggles auto start checkbox', async () => {
    renderWithProviders(<BatchJobModal isOpen={true} onClose={vi.fn()} />)
    
    const checkbox = screen.getByLabelText(/start jobs automatically/i)
    expect(checkbox).toBeChecked()
    
    fireEvent.click(checkbox)
    expect(checkbox).not.toBeChecked()
  })
  
  it('closes modal on cancel', async () => {
    const onClose = vi.fn()
    renderWithProviders(<BatchJobModal isOpen={true} onClose={onClose} />)
    
    fireEvent.click(screen.getByText('Cancel'))
    
    expect(onClose).toHaveBeenCalled()
  })
})
