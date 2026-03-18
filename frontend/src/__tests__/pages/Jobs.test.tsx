import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import Jobs from '../../pages/Jobs'
import { renderWithProviders } from '../../test/utils'

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  }
})

describe('Jobs Page', () => {
  it('renders page title', async () => {
    renderWithProviders(<Jobs />)
    expect(screen.getByText('Jobs')).toBeInTheDocument()
  })
  
  it('shows new job button', () => {
    renderWithProviders(<Jobs />)
    expect(screen.getByRole('button', { name: /new job/i })).toBeInTheDocument()
  })
  
  it('shows batch create button', () => {
    renderWithProviders(<Jobs />)
    expect(screen.getByRole('button', { name: /batch create/i })).toBeInTheDocument()
  })
})
