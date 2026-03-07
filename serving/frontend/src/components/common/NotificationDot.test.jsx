import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import NotificationDot from './NotificationDot'

describe('NotificationDot', () => {
  it('renders with default red color', () => {
    const { container } = render(<NotificationDot />)
    const dot = container.querySelector('.notification-dot')
    expect(dot).toBeTruthy()
    expect(dot.classList.contains('notification-dot--red')).toBe(true)
  })

  it('renders with amber color', () => {
    const { container } = render(<NotificationDot color="amber" />)
    const dot = container.querySelector('.notification-dot')
    expect(dot.classList.contains('notification-dot--amber')).toBe(true)
  })

  it('renders with blue color', () => {
    const { container } = render(<NotificationDot color="blue" />)
    const dot = container.querySelector('.notification-dot')
    expect(dot.classList.contains('notification-dot--blue')).toBe(true)
  })

  it('sets title and aria-label', () => {
    const { container } = render(<NotificationDot title="Test alert" />)
    const dot = container.querySelector('.notification-dot')
    expect(dot.getAttribute('title')).toBe('Test alert')
    expect(dot.getAttribute('aria-label')).toBe('Test alert')
  })
})
