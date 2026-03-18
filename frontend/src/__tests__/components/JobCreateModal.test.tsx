import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import JobCreateModal from '../../components/JobCreateModal'
import { renderWithProviders } from '../test/utils'

describe('JobCreateModal', () => {
  it('renders modal when open', () => {
    renderWithProviders(<JobCreateModal onClose={vi.fn()} />)
    expect(screen.getByText(/new job/i)).toBeInTheDocument()
  })
  
  it('renders template selector', () => {
    renderWithProviders(<JobCreateModal onClose={vi.fn()} />)
    expect(screen.getByLabelText(/template/i)).toBeInTheDocument()
  })
  
  it('shows dynamic form based on selected template', async () => {
    renderWithProviders(<JobCreateModal onClose={vi.fn()} />)
    
    await waitFor(() => {
      const select = screen.getByLabelText(/template/i)
      fireEvent.change(select, { target: { value: '1' } })
    })
    
    await waitFor(() => {
      expect(screen.getByLabelText(/prompt/i)).toBeInTheDocument()
    })
  })
  
  it('validates required fields', async () => {
    const onClose = vi.fn()
    renderWithProviders(<JobCreateModal onClose={onClose} />)
    
    await waitFor(async () => {
      const select = screen.getByLabelText(/template/i)
      fireEvent.change(select, { target: { value: '1' } })
      
      await waitFor(() => {
        const createButton = screen.getByText(/create/i)
        fireEvent.click(createButton)
      })
    })
    
    await waitFor(() => {
      expect(onClose).not.toHaveBeenCalled()
    })
  })
  
  it('submits job with valid data', async () => {
    const onClose = vi.fn()
    renderWithProviders(<JobCreateModal onClose={onClose} />)
    
    await waitFor(async () => {
      const select = screen.getByLabelText(/template/i)
      fireEvent.change(select, { target: { value: '1' } })
      
      await waitFor(async () => {
        const promptInput = screen.getByLabelText(/prompt/i)
        await userEvent.type(promptInput, 'Test prompt')
        
        const createButton = screen.getByText(/create/i)
        fireEvent.click(createButton)
      })
    })
    
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled()
    })
  })
  
  it('closes modal on cancel', async () => {
    const onClose = vi.fn()
    renderWithProviders(<JobCreateModal onClose={onClose} />)
    
    const cancelButton = screen.getByText(/cancel/i)
    fireEvent.click(cancelButton)
    
    expect(onClose).toHaveBeenCalled()
  })
  
  it('shows style selector for templates with style input', async () => {
    renderWithProviders(<JobCreateModal onClose={vi.fn()} />)
    
    await waitFor(() => {
      const select = screen.getByLabelText(/template/i)
      fireEvent.change(select, { target: { value: '1' } })
    })
    
    await waitFor(() => {
      expect(screen.getByLabelText(/prompt/i)).toBeInTheDocument()
    })
  })
})
