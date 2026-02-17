import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ActiveWorkView from './ActiveWorkView'

// Mock sub-components used by ActiveWorkView
vi.mock('../common/Badge', () => ({
  default: ({ variant, children }) => <span data-testid="badge" data-variant={variant}>{children}</span>,
  StatusBadge: ({ status }) => <span>{status}</span>,
}))

vi.mock('../common/Spinner', () => ({
  default: () => <div data-testid="spinner">Loading...</div>,
}))

function makeItem(overrides = {}) {
  return {
    issue_id: `issue-${Math.random().toString(36).slice(2, 8)}`,
    title: 'Test Item',
    priority: 'P2',
    status: 'in_progress',
    assigned_to: null,
    depends_on: [],
    ...overrides,
  }
}

describe('ActiveWorkView', () => {
  it('returns null when no data and not loading', () => {
    const { container } = render(<ActiveWorkView data={null} loading={false} />)
    expect(container.innerHTML).toBe('')
  })

  it('shows loading spinner when loading without data', () => {
    render(<ActiveWorkView data={null} loading={true} />)
    expect(screen.getByTestId('spinner')).toBeDefined()
  })

  it('renders three columns', () => {
    const data = { running_items: [], queued_items: [], blocked_items: [] }
    render(<ActiveWorkView data={data} loading={false} />)

    expect(screen.getByText('Running')).toBeDefined()
    expect(screen.getByText('Up Next')).toBeDefined()
    expect(screen.getByText('Blocked')).toBeDefined()
  })

  it('shows empty messages when columns have no items', () => {
    const data = { running_items: [], queued_items: [], blocked_items: [] }
    render(<ActiveWorkView data={data} loading={false} />)

    expect(screen.getByText('No items running')).toBeDefined()
    expect(screen.getByText('No items queued')).toBeDefined()
    expect(screen.getByText('No blocked items')).toBeDefined()
  })

  it('renders running items', () => {
    const data = {
      running_items: [makeItem({ title: 'Running task', priority: 'P1' })],
      queued_items: [],
      blocked_items: [],
    }
    render(<ActiveWorkView data={data} loading={false} />)

    expect(screen.getByText('Running task')).toBeDefined()
    expect(screen.getByText('P1')).toBeDefined()
  })

  it('renders queued items', () => {
    const data = {
      running_items: [],
      queued_items: [makeItem({ title: 'Queued task' })],
      blocked_items: [],
    }
    render(<ActiveWorkView data={data} loading={false} />)

    expect(screen.getByText('Queued task')).toBeDefined()
  })

  it('renders blocked items with dependency count', () => {
    const data = {
      running_items: [],
      queued_items: [],
      blocked_items: [
        makeItem({ title: 'Blocked task', depends_on: ['dep-1', 'dep-2'] }),
      ],
    }
    render(<ActiveWorkView data={data} loading={false} />)

    expect(screen.getByText('Blocked task')).toBeDefined()
    expect(screen.getByText('needs 2 deps')).toBeDefined()
  })

  it('shows singular "dep" for single dependency', () => {
    const data = {
      running_items: [],
      queued_items: [],
      blocked_items: [
        makeItem({ title: 'Blocked', depends_on: ['dep-1'] }),
      ],
    }
    render(<ActiveWorkView data={data} loading={false} />)

    expect(screen.getByText('needs 1 dep')).toBeDefined()
  })

  it('shows item number as #N when available', () => {
    const data = {
      running_items: [makeItem({ number: 42, title: 'Numbered' })],
      queued_items: [],
      blocked_items: [],
    }
    render(<ActiveWorkView data={data} loading={false} />)

    expect(screen.getByText('#42')).toBeDefined()
  })

  it('shows first 8 chars of issue_id when no number', () => {
    const data = {
      running_items: [makeItem({ issue_id: 'abcdefghijklmnop', title: 'ID item' })],
      queued_items: [],
      blocked_items: [],
    }
    render(<ActiveWorkView data={data} loading={false} />)

    expect(screen.getByText('abcdefgh')).toBeDefined()
  })

  it('shows truncated assignee', () => {
    const data = {
      running_items: [makeItem({ assigned_to: 'very-long-username-here' })],
      queued_items: [],
      blocked_items: [],
    }
    render(<ActiveWorkView data={data} loading={false} />)

    expect(screen.getByText('very-long-us')).toBeDefined()
  })

  it('calls onItemClick when item clicked', () => {
    const onItemClick = vi.fn()
    const item = makeItem({ title: 'Click me' })
    const data = { running_items: [item], queued_items: [], blocked_items: [] }
    render(<ActiveWorkView data={data} loading={false} onItemClick={onItemClick} />)

    fireEvent.click(screen.getByText('Click me'))
    expect(onItemClick).toHaveBeenCalledWith(item)
  })

  it('shows column item counts', () => {
    const data = {
      running_items: [makeItem(), makeItem()],
      queued_items: [makeItem()],
      blocked_items: [],
    }
    render(<ActiveWorkView data={data} loading={false} />)

    expect(screen.getByText('2')).toBeDefined()
    expect(screen.getByText('1')).toBeDefined()
  })

  it('uses correct badge variant for priorities', () => {
    const data = {
      running_items: [
        makeItem({ priority: 'P0', title: 'P0 item' }),
        makeItem({ priority: 'P3', title: 'P3 item' }),
      ],
      queued_items: [],
      blocked_items: [],
    }
    render(<ActiveWorkView data={data} loading={false} />)

    const badges = screen.getAllByTestId('badge')
    const p0Badge = badges.find(b => b.textContent === 'P0')
    const p3Badge = badges.find(b => b.textContent === 'P3')
    expect(p0Badge.getAttribute('data-variant')).toBe('error')
    expect(p3Badge.getAttribute('data-variant')).toBe('info')
  })
})
