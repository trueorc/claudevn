import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
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

function makeBucket(overrides = {}) {
  return {
    bucket_id: `bucket-${Math.random().toString(36).slice(2, 8)}`,
    rank: 1,
    definition: { name: 'Critical', description: 'Critical fixes' },
    items: [{ item_id: 'i1' }, { item_id: 'i2' }],
    ...overrides,
  }
}

describe('WhyThisOrder', () => {
  it('returns null when no buckets and no traces', () => {
    const { container } = render(<WhyThisOrder buckets={[]} traces={[]} traceCount={0} />)
    expect(container.innerHTML).toBe('')
  })

  it('shows Execution Order header', () => {
    const buckets = [makeBucket()]
    render(<WhyThisOrder buckets={buckets} traces={[]} traceCount={0} />)
    expect(screen.getByText('Execution Order')).toBeDefined()
  })

  it('shows ordering explanation when buckets exist', () => {
    const buckets = [makeBucket()]
    render(<WhyThisOrder buckets={buckets} traces={[]} traceCount={0} />)
    expect(screen.getByText(/Items are ordered by bucket rank/)).toBeDefined()
  })

  it('shows fallback when no buckets but has traces', () => {
    const traces = [makeTrace()]
    render(<WhyThisOrder buckets={[]} traces={traces} traceCount={1} />)
    expect(screen.getByText(/No bucket tree defined/)).toBeDefined()
  })

  it('renders bucket sequence sorted by rank', () => {
    const buckets = [
      makeBucket({ rank: 2, definition: { name: 'Medium', description: '' } }),
      makeBucket({ rank: 1, definition: { name: 'Critical', description: '' } }),
    ]
    render(<WhyThisOrder buckets={buckets} traces={[]} traceCount={0} />)

    expect(screen.getByText('Critical')).toBeDefined()
    expect(screen.getByText('Medium')).toBeDefined()
    expect(screen.getByText('#1')).toBeDefined()
    expect(screen.getByText('#2')).toBeDefined()
  })

  it('shows item count per bucket', () => {
    const buckets = [
      makeBucket({ items: [{ item_id: 'a' }, { item_id: 'b' }, { item_id: 'c' }] }),
    ]
    render(<WhyThisOrder buckets={buckets} traces={[]} traceCount={0} />)
    expect(screen.getByText('3 items')).toBeDefined()
  })

  it('shows singular "item" for count of 1', () => {
    const buckets = [
      makeBucket({ items: [{ item_id: 'a' }] }),
    ]
    render(<WhyThisOrder buckets={buckets} traces={[]} traceCount={0} />)
    expect(screen.getByText('1 item')).toBeDefined()
  })

  it('shows bucket description', () => {
    const buckets = [
      makeBucket({ definition: { name: 'Test', description: 'Test description' } }),
    ]
    render(<WhyThisOrder buckets={buckets} traces={[]} traceCount={0} />)
    expect(screen.getByText('Test description')).toBeDefined()
  })

  it('falls back to bucket_id when no definition name', () => {
    const buckets = [
      makeBucket({ bucket_id: 'my-bucket', definition: undefined }),
    ]
    render(<WhyThisOrder buckets={buckets} traces={[]} traceCount={0} />)
    expect(screen.getByText('my-bucket')).toBeDefined()
  })

  it('renders traces section as "Recent Decisions" collapsed by default', () => {
    const traces = [makeTrace()]
    render(<WhyThisOrder buckets={[makeBucket()]} traces={traces} traceCount={1} />)

    expect(screen.getByText('Recent Decisions')).toBeDefined()
    expect(screen.queryByText('Moved task to front of queue')).toBeNull()
  })

  it('expands traces on header click', () => {
    const traces = [makeTrace({ decision_summary: 'Reordered queue' })]
    render(<WhyThisOrder buckets={[makeBucket()]} traces={traces} traceCount={1} />)

    fireEvent.click(screen.getByText('Recent Decisions'))
    expect(screen.getByText('Reordered queue')).toBeDefined()
  })

  it('collapses traces on second click', () => {
    const traces = [makeTrace({ decision_summary: 'Reordered' })]
    render(<WhyThisOrder buckets={[makeBucket()]} traces={traces} traceCount={1} />)

    const header = screen.getByText('Recent Decisions')
    fireEvent.click(header)
    expect(screen.getByText('Reordered')).toBeDefined()

    fireEvent.click(header)
    expect(screen.queryByText('Reordered')).toBeNull()
  })

  it('shows trace count with singular "decision"', () => {
    render(<WhyThisOrder buckets={[makeBucket()]} traces={[makeTrace()]} traceCount={1} />)
    expect(screen.getByText('1 decision')).toBeDefined()
  })

  it('shows trace count with plural "decisions"', () => {
    render(<WhyThisOrder buckets={[makeBucket()]} traces={[makeTrace(), makeTrace()]} traceCount={5} />)
    expect(screen.getByText('5 decisions')).toBeDefined()
  })

  it('renders decision type labels correctly', () => {
    const traces = [
      makeTrace({ decision_type: 'profile_shift', decision_summary: 'Profile changed' }),
    ]
    render(<WhyThisOrder buckets={[]} traces={traces} traceCount={1} />)
    fireEvent.click(screen.getByText('Recent Decisions'))
    expect(screen.getByText('Profile Shift')).toBeDefined()
  })

  it('shows trigger text when present', () => {
    const traces = [makeTrace({ trigger: 'User requested priority change' })]
    render(<WhyThisOrder buckets={[]} traces={traces} traceCount={1} />)
    fireEvent.click(screen.getByText('Recent Decisions'))
    expect(screen.getByText('User requested priority change')).toBeDefined()
  })

  it('renders multiple traces', () => {
    const traces = [
      makeTrace({ decision_summary: 'First decision' }),
      makeTrace({ decision_summary: 'Second decision' }),
    ]
    render(<WhyThisOrder buckets={[]} traces={traces} traceCount={2} />)
    fireEvent.click(screen.getByText('Recent Decisions'))
    expect(screen.getByText('First decision')).toBeDefined()
    expect(screen.getByText('Second decision')).toBeDefined()
  })

  it('applies rank-based CSS classes to bucket rank badges', () => {
    const buckets = [
      makeBucket({ rank: 1, definition: { name: 'B1', description: '' } }),
      makeBucket({ rank: 3, definition: { name: 'B3', description: '' } }),
    ]
    render(<WhyThisOrder buckets={buckets} traces={[]} traceCount={0} />)
    const rank1 = screen.getByText('#1')
    const rank3 = screen.getByText('#3')
    expect(rank1.className).toContain('bucket-badge-rank-1')
    expect(rank3.className).toContain('bucket-badge-rank-3')
  })
})
