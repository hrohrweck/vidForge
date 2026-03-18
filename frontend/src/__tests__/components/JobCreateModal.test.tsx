import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import JobCreateModal from '../../components/JobCreateModal'
import { renderWithProviders } from '../../test/utils'

describe('JobCreateModal', () => {
  it('renders modal', () => {
    renderWithProviders(<JobCreateModal onClose={vi.fn()} />)
    expect(screen.getByText(/new job/i)).toBeInTheDocument()
  })
  
  it('renders template selector', () => {
    renderWithProviders(<JobCreateModal onClose={vi.fn()} />)
    expect(screen.getByLabelText(/template/i)).toBeInTheDocument()
  })
  
  it('shows cancel button', () => {
    renderWithProviders(<JobCreateModal onClose={vi.fn()} />)
    expect(screen.getByText(/cancel/i)).toBeInTheDocument()
  })
  
  it('shows create button', () => {
    renderWithProviders(<JobCreateModal onClose={vi.fn()} />)
    expect(screen.getByRole('button', { name: /create job/i })).toBeInTheDocument()
  })
})
