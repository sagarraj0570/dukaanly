import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { Login } from './Login'

// Mock 3D AuthScene to avoid WebGL context requirements in jsdom
vi.mock('@/components/three/AuthScene', () => ({
  default: () => <div data-testid="mock-auth-scene">Auth 3D Scene</div>,
  AuthScene: () => <div data-testid="mock-auth-scene">Auth 3D Scene</div>,
}))

const renderLogin = () => {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  )
}

describe('Login Page Redesign', () => {
  it('renders sign in tab, form fields, and quick demo access buttons', () => {
    renderLogin()

    // Title and tabs
    expect(screen.getByRole('heading', { name: /welcome back/i })).toBeTruthy()
    expect(screen.getByRole('tab', { name: /sign in/i })).toBeTruthy()
    expect(screen.getByRole('tab', { name: /create account/i })).toBeTruthy()

    // Inputs
    expect(screen.getByLabelText(/email address/i)).toBeTruthy()
    expect(screen.getByLabelText(/^password$/i)).toBeTruthy()

    // Quick demo access buttons
    expect(screen.getByRole('button', { name: /log in as demo customer/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /log in as demo shop owner/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /log in as demo rider/i })).toBeTruthy()

    // Customer-facing value chips in left brand composition
    expect(screen.getByText(/real shops, real prices/i)).toBeTruthy()
    expect(screen.getByText(/live order tracking/i)).toBeTruthy()
    expect(screen.getByText(/fast local delivery/i)).toBeTruthy()
  })

  it('switches to create account mode when clicking Create Account tab', () => {
    renderLogin()

    const createAccountTab = screen.getByRole('tab', { name: /create account/i })
    fireEvent.click(createAccountTab)

    expect(screen.getByRole('heading', { name: /join dukaanly/i })).toBeTruthy()
    expect(screen.getByLabelText(/full name/i)).toBeTruthy()
    expect(screen.getByLabelText(/phone/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: /create account & continue/i })).toBeTruthy()
  })

  it('populates fields when clicking demo access button', () => {
    renderLogin()

    const customerBtn = screen.getByRole('button', { name: /log in as demo customer/i })
    fireEvent.click(customerBtn)

    const emailInput = screen.getByLabelText(/email address/i) as HTMLInputElement
    expect(emailInput.value).toBe('customer@dukaanly.com')
  })
})
