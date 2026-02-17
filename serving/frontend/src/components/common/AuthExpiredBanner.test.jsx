import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import AuthExpiredBanner from './AuthExpiredBanner.jsx'

describe('AuthExpiredBanner', () => {
  it('renders the expiration message', () => {
    render(<AuthExpiredBanner onReauth={() => {}} />)
    expect(screen.getByText(/credentials have expired/i)).toBeInTheDocument()
  })

  it('renders a re-authenticate button', () => {
    render(<AuthExpiredBanner onReauth={() => {}} />)
    expect(screen.getByRole('button', { name: /re-authenticate/i })).toBeInTheDocument()
  })

  it('calls onReauth when button is clicked', () => {
    const onReauth = vi.fn()
    render(<AuthExpiredBanner onReauth={onReauth} />)

    fireEvent.click(screen.getByRole('button', { name: /re-authenticate/i }))
    expect(onReauth).toHaveBeenCalledOnce()
  })
})
