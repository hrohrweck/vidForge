import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Login from '../../pages/Login'
import { renderWithProviders } from '../../test/utils'

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  }
})

describe('Login Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders login form by default', () => {
    renderWithProviders(<Login />)
    expect(screen.getByText('VidForge')).toBeInTheDocument()
    expect(screen.getByText('Sign in to your account')).toBeInTheDocument()
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('toggles to register mode', () => {
    renderWithProviders(<Login />)
    
    fireEvent.click(screen.getByText(/don't have an account/i))
    
    expect(screen.getByText('Create a new account')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument()
  })

  it('shows validation error for empty fields', () => {
    renderWithProviders(<Login />)
    
    const submitButton = screen.getByRole('button', { name: /sign in/i })
    fireEvent.click(submitButton)
    
    const emailInput = screen.getByLabelText(/email/i)
    const passwordInput = screen.getByLabelText(/password/i)
    
    expect(emailInput).toBeRequired()
    expect(passwordInput).toBeRequired()
  })

  it('shows error message on login failure', async () => {
    renderWithProviders(<Login />)
    
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'wrong@example.com' },
    })
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'wrongpassword' },
    })
    
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    
    await waitFor(() => {
      expect(screen.getByText(/invalid email or password/i)).toBeInTheDocument()
    })
  })

  it('clears error when switching modes', () => {
    renderWithProviders(<Login />)
    
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'test@example.com' },
    })
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'wrongpassword' },
    })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    
    fireEvent.click(screen.getByText(/don't have an account/i))
    
    expect(screen.queryByText(/invalid email or password/i)).not.toBeInTheDocument()
  })
})

describe('Register Mode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows register form when toggled', () => {
    renderWithProviders(<Login />)
    
    fireEvent.click(screen.getByText(/don't have an account/i))
    
    expect(screen.getByText('Create a new account')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument()
  })

  it('shows error on registration failure', async () => {
    renderWithProviders(<Login />)
    
    fireEvent.click(screen.getByText(/don't have an account/i))
    
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'duplicate@example.com' },
    })
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'wrongpassword' },
    })
    
    fireEvent.click(screen.getByRole('button', { name: /create account/i }))
    
    await waitFor(() => {
      expect(screen.getByText(/registration failed/i)).toBeInTheDocument()
    })
  })

  it('toggles back to login mode', () => {
    renderWithProviders(<Login />)
    
    fireEvent.click(screen.getByText(/don't have an account/i))
    expect(screen.getByText('Create a new account')).toBeInTheDocument()
    
    fireEvent.click(screen.getByText(/already have an account/i))
    expect(screen.getByText('Sign in to your account')).toBeInTheDocument()
  })
})
