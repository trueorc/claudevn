import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import SummaryBar from './SummaryBar'

describe('SummaryBar', () => {
  it('returns null when no data and not loading', () => {
    const { container } = render(<SummaryBar data={null} loading={false} />)
    expect(container.innerHTML).toBe('')
  })

  it('shows loading state when loading without data', () => {
    render(<SummaryBar data={null} loading={true} />)
    expect(screen.getByText('Loading plan summary...')).toBeDefined()
  })

  it('renders stats with correct counts', () => {
    const data = {
      in_progress_count: 3,
      ready_count: 5,
      blocked_count: 2,
    }
    render(<SummaryBar data={data} loading={false} />)

    expect(screen.getByText('3')).toBeDefined()
    expect(screen.getByText('active')).toBeDefined()
    expect(screen.getByText('5')).toBeDefined()
    expect(screen.getByText('queued')).toBeDefined()
    expect(screen.getByText('2')).toBeDefined()
    expect(screen.getByText('blocked')).toBeDefined()
  })

  it('defaults missing counts to 0', () => {
    render(<SummaryBar data={{}} loading={false} />)

    const values = screen.getAllByText('0')
    expect(values.length).toBe(3)
  })

  it('shows focus summary when available', () => {
    const data = {
      in_progress_count: 1,
      ready_count: 2,
      blocked_count: 0,
      focus_summary: 'Testing and quality',
    }
    render(<SummaryBar data={data} loading={false} />)

    expect(screen.getByText('Testing and quality')).toBeDefined()
  })

  it('hides focus summary when it contains "unavailable"', () => {
    const data = {
      in_progress_count: 0,
      ready_count: 0,
      blocked_count: 0,
      focus_summary: 'Focus data unavailable',
    }
    render(<SummaryBar data={data} loading={false} />)

    expect(screen.queryByText('Focus data unavailable')).toBeNull()
  })

  it('hides focus summary when null', () => {
    const data = { in_progress_count: 0, ready_count: 0, blocked_count: 0, focus_summary: null }
    render(<SummaryBar data={data} loading={false} />)

    // No focus section rendered
    const focusEl = document.querySelector('.plan-summary-focus')
    expect(focusEl).toBeNull()
  })

  it('renders data even when loading is true', () => {
    const data = { in_progress_count: 1, ready_count: 0, blocked_count: 0 }
    render(<SummaryBar data={data} loading={true} />)

    // Should show the data, not the loading state
    expect(screen.getByText('1')).toBeDefined()
    expect(screen.getByText('active')).toBeDefined()
  })
})
