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
    key_factors: null,
    related_trace_ids: null,
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

  // --- Trace filtering: ordering vs other activity ---

  it('classifies task_movement as ordering trace and shows expanded', () => {
    const traces = [makeTrace({ decision_type: 'task_movement', decision_summary: 'Moved item A' })]
    render(<WhyThisOrder buckets={[makeBucket()]} traces={traces} traceCount={1} />)
    expect(screen.getByText('Ordering Decisions')).toBeDefined()
    // Ordering traces are expanded by default
    expect(screen.getByText('Moved item A')).toBeDefined()
  })

  it('classifies profile_shift as ordering trace', () => {
    const traces = [makeTrace({ decision_type: 'profile_shift', decision_summary: 'Profile changed' })]
    render(<WhyThisOrder buckets={[]} traces={traces} traceCount={1} />)
    expect(screen.getByText('Ordering Decisions')).toBeDefined()
    expect(screen.getByText('Profile Shift')).toBeDefined()
  })

  it('classifies bucket_reorganization as ordering trace', () => {
    const traces = [makeTrace({ decision_type: 'bucket_reorganization', decision_summary: 'Reorg happened' })]
    render(<WhyThisOrder buckets={[]} traces={traces} traceCount={1} />)
    expect(screen.getByText('Ordering Decisions')).toBeDefined()
    expect(screen.getByText('Reorganization')).toBeDefined()
  })

  it('classifies worker_assignment as other activity and shows collapsed', () => {
    const traces = [makeTrace({ decision_type: 'worker_assignment', decision_summary: 'Assigned worker' })]
    render(<WhyThisOrder buckets={[makeBucket()]} traces={traces} traceCount={1} />)
    expect(screen.getByText('Other Activity')).toBeDefined()
    // Other activity is collapsed by default
    expect(screen.queryByText('Assigned worker')).toBeNull()
  })

  it('expands other activity on click', () => {
    const traces = [makeTrace({ decision_type: 'worker_assignment', decision_summary: 'Assigned worker X' })]
    render(<WhyThisOrder buckets={[makeBucket()]} traces={traces} traceCount={1} />)
    fireEvent.click(screen.getByText('Other Activity'))
    expect(screen.getByText('Assigned worker X')).toBeDefined()
  })

  it('splits traces into ordering and other sections', () => {
    const traces = [
      makeTrace({ decision_type: 'task_movement', decision_summary: 'Moved item' }),
      makeTrace({ decision_type: 'worker_assignment', decision_summary: 'Assigned worker' }),
    ]
    render(<WhyThisOrder buckets={[makeBucket()]} traces={traces} traceCount={2} />)
    expect(screen.getByText('Ordering Decisions')).toBeDefined()
    expect(screen.getByText('Other Activity')).toBeDefined()
    // Ordering visible, other hidden
    expect(screen.getByText('Moved item')).toBeDefined()
    expect(screen.queryByText('Assigned worker')).toBeNull()
  })

  it('collapses ordering decisions on click', () => {
    const traces = [makeTrace({ decision_type: 'task_movement', decision_summary: 'Moved item Z' })]
    render(<WhyThisOrder buckets={[makeBucket()]} traces={traces} traceCount={1} />)
    expect(screen.getByText('Moved item Z')).toBeDefined()
    fireEvent.click(screen.getByText('Ordering Decisions'))
    expect(screen.queryByText('Moved item Z')).toBeNull()
  })

  // --- Key factors and triggers ---

  it('renders key_factors as list items', () => {
    const traces = [makeTrace({
      decision_type: 'task_movement',
      key_factors: ['Higher priority', 'Fewer dependencies'],
    })]
    render(<WhyThisOrder buckets={[]} traces={traces} traceCount={1} />)
    expect(screen.getByText('Higher priority')).toBeDefined()
    expect(screen.getByText('Fewer dependencies')).toBeDefined()
  })

  it('shows string trigger text', () => {
    const traces = [makeTrace({
      decision_type: 'bucket_reorganization',
      trigger: 'User requested priority change',
    })]
    render(<WhyThisOrder buckets={[]} traces={traces} traceCount={1} />)
    expect(screen.getByText('User requested priority change')).toBeDefined()
  })

  it('shows object trigger description', () => {
    const traces = [makeTrace({
      decision_type: 'bucket_reorganization',
      trigger: { description: 'Profile weight changed' },
    })]
    render(<WhyThisOrder buckets={[]} traces={traces} traceCount={1} />)
    expect(screen.getByText('Profile weight changed')).toBeDefined()
  })

  it('shows decision count in ordering header', () => {
    const traces = [
      makeTrace({ decision_type: 'task_movement' }),
      makeTrace({ decision_type: 'task_movement' }),
      makeTrace({ decision_type: 'task_movement' }),
    ]
    render(<WhyThisOrder buckets={[makeBucket()]} traces={traces} traceCount={3} />)
    expect(screen.getByText(/3 decisions/)).toBeDefined()
  })

  it('shows singular decision count', () => {
    const traces = [makeTrace({ decision_type: 'bucket_reorganization' })]
    render(<WhyThisOrder buckets={[makeBucket()]} traces={traces} traceCount={1} />)
    expect(screen.getByText(/1 decision/)).toBeDefined()
  })
})
