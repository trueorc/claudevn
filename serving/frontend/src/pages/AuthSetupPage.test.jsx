import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import AuthSetupPage from './AuthSetupPage.jsx'

const defaultProps = {
  status: 'not_configured',
  message: null,
  submitToken: vi.fn(),
}

function renderPage(overrides = {}) {
  return render(<AuthSetupPage {...defaultProps} {...overrides} />)
}

describe('AuthSetupPage', () => {
  describe('status labels', () => {
    it('shows user-friendly label for not_configured', () => {
      renderPage({ status: 'not_configured' })
      expect(screen.getByText('Token needed')).toBeInTheDocument()
    })

    it('shows user-friendly label for authenticated', () => {
      renderPage({ status: 'authenticated' })
      expect(screen.getByText('Connected')).toBeInTheDocument()
    })

    it('shows user-friendly label for expired', () => {
      renderPage({ status: 'expired' })
      expect(screen.getByText('Token expired')).toBeInTheDocument()
    })

    it('shows user-friendly label for error', () => {
      renderPage({ status: 'error' })
      expect(screen.getByText('Connection error')).toBeInTheDocument()
    })

    it('maps disabled status to status-info CSS class', () => {
      renderPage({ status: 'disabled' })
      const badge = document.querySelector('.auth-status-badge')
      expect(badge).toHaveClass('status-info')
      expect(badge).toHaveTextContent('Ready')
    })
  })

  describe('token input', () => {
    it('shows token input field', () => {
      renderPage()
      expect(screen.getByPlaceholderText('sk-ant-oat01-...')).toBeInTheDocument()
    })

    it('shows setup instructions', () => {
      renderPage()
      expect(screen.getByText(/claude setup-token/)).toBeInTheDocument()
    })

    it('shows submit button', () => {
      renderPage()
      expect(screen.getByRole('button', { name: /submit/i })).toBeInTheDocument()
    })

    it('disables submit button when input is empty', () => {
      renderPage()
      const btn = screen.getByRole('button', { name: /submit/i })
      expect(btn).toBeDisabled()
    })

    it('shows validation error for invalid token prefix', () => {
      renderPage()
      const input = screen.getByPlaceholderText('sk-ant-oat01-...')
      fireEvent.change(input, { target: { value: 'invalid-token' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))
      expect(screen.getByText(/must start with/i)).toBeInTheDocument()
    })

    it('calls submitToken with valid token', () => {
      const submitToken = vi.fn()
      renderPage({ submitToken })
      const input = screen.getByPlaceholderText('sk-ant-oat01-...')
      fireEvent.change(input, { target: { value: 'sk-ant-oat01-test-token' } })
      fireEvent.click(screen.getByRole('button', { name: /submit/i }))
      expect(submitToken).toHaveBeenCalledWith('sk-ant-oat01-test-token')
    })
  })

  describe('error state', () => {
    it('shows error message', () => {
      renderPage({ status: 'error', message: 'Something broke' })
      expect(screen.getByText('Something broke')).toBeInTheDocument()
    })

    it('renders error container with role="alert"', () => {
      renderPage({ status: 'error', message: 'Something broke' })
      const alert = screen.getByRole('alert')
      expect(alert).toBeInTheDocument()
      expect(alert).toHaveTextContent('Something broke')
    })
  })
})
