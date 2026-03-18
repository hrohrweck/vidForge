import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BatchJobModal } from '../../components/BatchJobModal'
import { renderWithProviders } from '../../test/utils'

describe('BatchJobModal', () => {
  it('renders modal when open', () => {
    renderWithProviders(<BatchJobModal isOpen={true} onClose={vi.fn()} />)
    expect(screen.getByText('Create Batch Jobs')).toBeInTheDocument()
  })
  
  it('does not render when closed', () => {
    renderWithProviders(<BatchJobModal isOpen={false} onClose={vi.fn()} />)
    expect(screen.queryByText('Create Batch Jobs')).not.toBeInTheDocument()
  })
  
  it('shows template selector', () => {
    renderWithProviders(<BatchJobModal isOpen={true} onClose={vi.fn()} />)
    expect(screen.getByLabelText(/template/i)).toBeInTheDocument()
  })
  
  it('shows manual input mode by default', () => {
    renderWithProviders(<BatchJobModal isOpen={true} onClose={vi.fn()} />)
    expect(screen.getByLabelText(/job inputs/i)).toBeInTheDocument()
  })
  
  it('shows cancel button', () => {
    renderWithProviders(<BatchJobModal isOpen={true} onClose={vi.fn()} />)
    expect(screen.getByText('Cancel')).toBeInTheDocument()
  })
  
  it('shows create button', () => {
    renderWithProviders(<BatchJobModal isOpen={true} onClose={vi.fn()} />)
    expect(screen.getByText('Create Jobs')).toBeInTheDocument()
  })
})
