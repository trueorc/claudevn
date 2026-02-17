import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import WhyThisOrder from './WhyThisOrder'

function makeTrace(overrides = {}) {
  return {
    trace_id: `trace-${Math.random().toString(36).slice(2, 8)}`,
    decision_type: 'task_movement',
    decision_summary: 'Moved task to front of queue',
    timestamp: new Date().toISOString(),
    trigger: null,
    ...overrides,
  }
}

describe('WhyThisOrder', () => {
  it('returns null when traces are empty', () => {
    const { container } = render(<WhyThisOrder traces={[]} traceCount={0} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders collapsed by default', () => {
    const traces = [makeTrace()]
    render(<WhyThisOrder traces={traces} traceCount={1} />)

    expect(screen.getByText('Why this order')).toBeDefined()
    // Trace content should not be visible
    expect(screen.queryByText('Moved task to front of queue')).toBeNull()
  })

  it('expands on header click to show traces', () => {
    const traces = [makeTrace({ decision_summary: 'Reordered queue' })]
    render(<WhyThisOrder traces={traces} traceCount={1} />)

    fireEvent.click(screen.getByText('Why this order'))
    expect(screen.getByText('Reordered queue')).toBeDefined()
  })

  it('collapses again on second click', () => {
    const traces = [makeTrace({ decision_summary: 'Reordered' })]
    render(<WhyThisOrder traces={traces} traceCount={1} />)

    const header = screen.getByText('Why this order')
    fireEvent.click(header) // expand
    expect(screen.getByText('Reordered')).toBeDefined()

    fireEvent.click(header) // collapse
    expect(screen.queryByText('Reordered')).toBeNull()
  })

  it('shows trace count with singular "decision"', () => {
    render(<WhyThisOrder traces={[makeTrace()]} traceCount={1} />)
    expect(screen.getByText('1 decision')).toBeDefined()
  })

  it('shows trace count with plural "decisions"', () => {
    render(<WhyThisOrder traces={[makeTrace(), makeTrace()]} traceCount={5} />)
    expect(screen.getByText('5 decisions')).toBeDefined()
  })

  it('renders decision type with correct label', () => {
    const traces = [
      makeTrace({ decision_type: 'profile_shift', decision_summary: 'Profile changed' }),
    ]
    render(<WhyThisOrder traces={traces} traceCount={1} />)
    fireEvent.click(screen.getByText('Why this order'))

    expect(screen.getByText('Profile Shift')).toBeDefined()
  })

  it('renders all decision type labels correctly', () => {
    const types = [
      { type: 'bucket_reorganization', label: 'Reorganization' },
      { type: 'conflict_identified', label: 'Conflict Found' },
      { type: 'conflict_resolved', label: 'Conflict Resolved' },
      { type: 'worker_assignment', label: 'Assignment' },
    ]

    types.forEach(({ type, label }) => {
      const traces = [makeTrace({ decision_type: type, decision_summary: `summary-${type}` })]
      const { unmount } = render(<WhyThisOrder traces={traces} traceCount={1} />)
      fireEvent.click(screen.getByText('Why this order'))
      expect(screen.getByText(label)).toBeDefined()
      unmount()
    })
  })

  it('shows trigger text when present', () => {
    const traces = [
      makeTrace({ trigger: 'User requested priority change' }),
    ]
    render(<WhyThisOrder traces={traces} traceCount={1} />)
    fireEvent.click(screen.getByText('Why this order'))

    expect(screen.getByText('User requested priority change')).toBeDefined()
  })

  it('does not show trigger when null', () => {
    const traces = [makeTrace({ trigger: null, decision_summary: 'No trigger trace' })]
    render(<WhyThisOrder traces={traces} traceCount={1} />)
    fireEvent.click(screen.getByText('Why this order'))

    expect(screen.getByText('No trigger trace')).toBeDefined()
    // Only the summary and type label should be visible, no extra paragraphs
    const traceCards = document.querySelectorAll('.plan-trace-trigger')
    expect(traceCards.length).toBe(0)
  })

  it('renders multiple traces', () => {
    const traces = [
      makeTrace({ decision_summary: 'First decision' }),
      makeTrace({ decision_summary: 'Second decision' }),
      makeTrace({ decision_summary: 'Third decision' }),
    ]
    render(<WhyThisOrder traces={traces} traceCount={3} />)
    fireEvent.click(screen.getByText('Why this order'))

    expect(screen.getByText('First decision')).toBeDefined()
    expect(screen.getByText('Second decision')).toBeDefined()
    expect(screen.getByText('Third decision')).toBeDefined()
  })

  it('shows "just now" for very recent timestamps', () => {
    const traces = [makeTrace({ timestamp: new Date().toISOString() })]
    render(<WhyThisOrder traces={traces} traceCount={1} />)
    fireEvent.click(screen.getByText('Why this order'))

    expect(screen.getByText('just now')).toBeDefined()
  })

  it('shows relative time for older timestamps', () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString()
    const traces = [makeTrace({ timestamp: twoHoursAgo })]
    render(<WhyThisOrder traces={traces} traceCount={1} />)
    fireEvent.click(screen.getByText('Why this order'))

    expect(screen.getByText('2h ago')).toBeDefined()
  })

  it('falls back to decision_type as label for unknown types', () => {
    const traces = [makeTrace({ decision_type: 'custom_type', decision_summary: 'Custom' })]
    render(<WhyThisOrder traces={traces} traceCount={1} />)
    fireEvent.click(screen.getByText('Why this order'))

    expect(screen.getByText('custom_type')).toBeDefined()
  })
})
