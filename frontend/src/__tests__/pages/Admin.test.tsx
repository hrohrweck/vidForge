import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import Admin from '../../pages/Admin'
import { renderWithProviders } from '../../test/utils'

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  }
})

describe('Admin Page', () => {
  it('shows loading state initially', () => {
    renderWithProviders(<Admin />, { superuser: true })
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })
})
