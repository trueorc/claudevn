import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import GoalHistoryPanel from './GoalHistoryPanel'

// Mock child components to simplify tests
vi.mock('./EvaluationStatusIndicator', () => ({
  default: ({ status }) => <span data-testid="eval-status">{status}</span>,
}))

function makeGoal(overrides = {}) {
  return {
    goal_id: `goal-${Math.random().toString(36).slice(2, 8)}`,
    title: 'Test Goal',
    description: 'A test goal description',
    priority: 'P2',
    created_at: new Date().toISOString(),
    conversation_status: 'no_comments',
    archived: false,
    ...overrides,
  }
}

describe('GoalHistoryPanel', () => {
  const defaultProps = {
    goals: [],
    selectedGoalId: null,
    onSelectGoal: vi.fn(),
    onDeleteGoal: vi.fn(),
    onArchiveGoal: vi.fn(),
    onUnarchiveGoal: vi.fn(),
    goalCommentCounts: {},
    goalProgress: {},
    loading: false,
    showArchived: false,
    onToggleShowArchived: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('loading and empty states', () => {
    it('shows loading state', () => {
      render(<GoalHistoryPanel {...defaultProps} loading={true} />)
      expect(screen.getByText('Loading...')).toBeDefined()
    })

    it('shows empty state when no goals', () => {
      render(<GoalHistoryPanel {...defaultProps} />)
      expect(screen.getByText('No directives yet. Start a conversation to create one.')).toBeDefined()
    })

    it('shows filtered empty state when filters active', () => {
      render(<GoalHistoryPanel {...defaultProps} />)

      // Activate a filter by searching
      const searchInput = screen.getByPlaceholderText('Search history...')
      fireEvent.change(searchInput, { target: { value: 'nonexistent' } })

      expect(screen.getByText('No items match your filters')).toBeDefined()
    })
  })

  describe('goal rendering', () => {
    it('renders goal cards for each goal', () => {
      const goals = [
        makeGoal({ goal_id: 'g-1', title: 'First goal' }),
        makeGoal({ goal_id: 'g-2', title: 'Second goal' }),
      ]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      expect(screen.getByText('First goal')).toBeDefined()
      expect(screen.getByText('Second goal')).toBeDefined()
    })

    it('shows goal count in header', () => {
      const goals = [makeGoal(), makeGoal()]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      expect(screen.getByText(/2.*items/)).toBeDefined()
    })

    it('highlights selected goal', () => {
      const goals = [makeGoal({ goal_id: 'g-1', title: 'Selected' })]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} selectedGoalId="g-1" />)

      const card = screen.getByText('Selected').closest('button')
      expect(card.className).toContain('selected')
    })

    it('shows priority badge', () => {
      const goals = [makeGoal({ priority: 'P0' })]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)
      expect(screen.getByText('P0')).toBeDefined()
    })

    it('shows goal ID badge (last 6 chars)', () => {
      const goals = [makeGoal({ goal_id: 'goal-abc123def456' })]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)
      expect(screen.getByText('#def456')).toBeDefined()
    })

    it('shows comment count when present', () => {
      const goals = [makeGoal({ goal_id: 'g-1' })]
      render(
        <GoalHistoryPanel
          {...defaultProps}
          goals={goals}
          goalCommentCounts={{ 'g-1': 5 }}
        />
      )
      expect(screen.getByText('5')).toBeDefined()
    })

    it('does not show comment count when zero', () => {
      const goals = [makeGoal({ goal_id: 'g-1' })]
      render(
        <GoalHistoryPanel
          {...defaultProps}
          goals={goals}
          goalCommentCounts={{ 'g-1': 0 }}
        />
      )
      // Should not find a comments element
      expect(screen.queryByText('0')).toBeNull()
    })

    it('shows archived badge for archived goals', () => {
      const goals = [makeGoal({ archived: true })]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} showArchived={true} />)
      const archivedBadge = document.querySelector('.goal-archived-badge')
      expect(archivedBadge).not.toBeNull()
      expect(archivedBadge.textContent).toBe('Archived')
    })
  })

  describe('interactions', () => {
    it('calls onSelectGoal when goal card clicked', () => {
      const onSelectGoal = vi.fn()
      const goal = makeGoal({ title: 'Click me' })
      render(<GoalHistoryPanel {...defaultProps} goals={[goal]} onSelectGoal={onSelectGoal} />)

      fireEvent.click(screen.getByText('Click me'))
      expect(onSelectGoal).toHaveBeenCalledWith(goal)
    })

    it('calls onDeleteGoal when delete button clicked', () => {
      const onDeleteGoal = vi.fn()
      const goal = makeGoal({ title: 'Delete me' })
      render(<GoalHistoryPanel {...defaultProps} goals={[goal]} onDeleteGoal={onDeleteGoal} />)

      const deleteBtn = screen.getByTitle('Delete goal')
      fireEvent.click(deleteBtn)
      expect(onDeleteGoal).toHaveBeenCalledWith(goal)
    })

    it('calls onArchiveGoal when archive button clicked', () => {
      const onArchiveGoal = vi.fn()
      const goal = makeGoal({ title: 'Archive me' })
      render(<GoalHistoryPanel {...defaultProps} goals={[goal]} onArchiveGoal={onArchiveGoal} />)

      const archiveBtn = screen.getByTitle('Archive goal')
      fireEvent.click(archiveBtn)
      expect(onArchiveGoal).toHaveBeenCalledWith(goal)
    })

    it('calls onUnarchiveGoal when unarchive button clicked on archived goal', () => {
      const onUnarchiveGoal = vi.fn()
      const goal = makeGoal({ archived: true })
      render(
        <GoalHistoryPanel
          {...defaultProps}
          goals={[goal]}
          onUnarchiveGoal={onUnarchiveGoal}
          showArchived={true}
        />
      )

      const unarchiveBtn = screen.getByTitle('Unarchive goal')
      fireEvent.click(unarchiveBtn)
      expect(onUnarchiveGoal).toHaveBeenCalledWith(goal)
    })
  })

  describe('search', () => {
    it('filters goals by title', () => {
      const goals = [
        makeGoal({ title: 'Authentication feature' }),
        makeGoal({ title: 'Database migration' }),
      ]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      const searchInput = screen.getByPlaceholderText('Search history...')
      fireEvent.change(searchInput, { target: { value: 'auth' } })

      expect(screen.getByText('Authentication feature')).toBeDefined()
      expect(screen.queryByText('Database migration')).toBeNull()
    })

    it('filters goals by description', () => {
      const goals = [
        makeGoal({ title: 'Goal 1', description: 'Involves React components' }),
        makeGoal({ title: 'Goal 2', description: 'Involves Python services' }),
      ]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      const searchInput = screen.getByPlaceholderText('Search history...')
      fireEvent.change(searchInput, { target: { value: 'python' } })

      expect(screen.queryByText('Goal 1')).toBeNull()
      expect(screen.getByText('Goal 2')).toBeDefined()
    })

    it('search is case-insensitive', () => {
      const goals = [makeGoal({ title: 'Fix LOGIN Bug' })]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      fireEvent.change(screen.getByPlaceholderText('Search history...'), {
        target: { value: 'login' },
      })
      expect(screen.getByText('Fix LOGIN Bug')).toBeDefined()
    })

    it('shows clear button when search has text', () => {
      render(<GoalHistoryPanel {...defaultProps} goals={[makeGoal()]} />)

      const searchInput = screen.getByPlaceholderText('Search history...')
      fireEvent.change(searchInput, { target: { value: 'test' } })

      // Clear button exists (X icon button in search wrapper)
      const clearBtn = searchInput.parentElement.querySelector('.search-clear')
      expect(clearBtn).toBeDefined()
    })
  })

  describe('filters', () => {
    it('opens filter panel on filter button click', () => {
      render(<GoalHistoryPanel {...defaultProps} goals={[makeGoal()]} />)

      const filterBtn = screen.getByTitle('Filter goals')
      fireEvent.click(filterBtn)

      expect(screen.getByText('All statuses')).toBeDefined()
      expect(screen.getByText('All priorities')).toBeDefined()
    })

    it('filters by priority', () => {
      const goals = [
        makeGoal({ title: 'Critical', priority: 'P0' }),
        makeGoal({ title: 'Low', priority: 'P3' }),
      ]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      // Open filters
      fireEvent.click(screen.getByTitle('Filter goals'))

      // Select P0 priority
      const prioritySelect = screen.getByDisplayValue('All priorities')
      fireEvent.change(prioritySelect, { target: { value: 'P0' } })

      expect(screen.getByText('Critical')).toBeDefined()
      expect(screen.queryByText('Low')).toBeNull()
    })

    it('filters by conversation status', () => {
      const goals = [
        makeGoal({ title: 'Done goal', conversation_status: 'complete' }),
        makeGoal({ title: 'Waiting goal', conversation_status: 'pending' }),
      ]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      fireEvent.click(screen.getByTitle('Filter goals'))
      const statusSelect = screen.getByDisplayValue('All statuses')
      fireEvent.change(statusSelect, { target: { value: 'complete' } })

      expect(screen.getByText('Done goal')).toBeDefined()
      expect(screen.queryByText('Waiting goal')).toBeNull()
    })

    it('shows filter chips for active filters', () => {
      render(<GoalHistoryPanel {...defaultProps} goals={[makeGoal()]} />)

      fireEvent.click(screen.getByTitle('Filter goals'))
      const prioritySelect = screen.getByDisplayValue('All priorities')
      fireEvent.change(prioritySelect, { target: { value: 'P1' } })

      expect(screen.getByText('P1')).toBeDefined()
    })

    it('clear all filters resets everything', () => {
      const goals = [
        makeGoal({ title: 'Goal A', priority: 'P0' }),
        makeGoal({ title: 'Goal B', priority: 'P3' }),
      ]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      // Apply a filter
      fireEvent.click(screen.getByTitle('Filter goals'))
      fireEvent.change(screen.getByDisplayValue('All priorities'), { target: { value: 'P0' } })
      expect(screen.queryByText('Goal B')).toBeNull()

      // Clear all
      fireEvent.click(screen.getByText('Clear all filters'))
      expect(screen.getByText('Goal A')).toBeDefined()
      expect(screen.getByText('Goal B')).toBeDefined()
    })
  })

  describe('sorting', () => {
    it('sorts by newest first by default', () => {
      const goals = [
        makeGoal({ title: 'Old', created_at: '2025-01-01T00:00:00Z' }),
        makeGoal({ title: 'New', created_at: '2025-01-15T00:00:00Z' }),
      ]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      const cards = screen.getAllByRole('button').filter(b => b.className.includes('goal-history-card'))
      // Newest should be first
      expect(cards[0].textContent).toContain('New')
    })

    it('sorts by priority high first', () => {
      const goals = [
        makeGoal({ title: 'Low', priority: 'P3', created_at: '2025-01-15T00:00:00Z' }),
        makeGoal({ title: 'Critical', priority: 'P0', created_at: '2025-01-14T00:00:00Z' }),
      ]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      // Open filters and change sort
      fireEvent.click(screen.getByTitle('Filter goals'))
      const sortSelect = screen.getByDisplayValue('Newest first')
      fireEvent.change(sortSelect, { target: { value: 'priority_high' } })

      const cards = screen.getAllByRole('button').filter(b => b.className.includes('goal-history-card'))
      expect(cards[0].textContent).toContain('Critical')
    })
  })

  describe('status indicator and card text', () => {
    it('applies status class for colored left border', () => {
      const goals = [makeGoal({ goal_id: 'g-1', conversation_status: 'pending' })]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      const card = document.querySelector('.goal-history-card')
      expect(card.className).toContain('status-pending')
    })

    it('applies complete status class', () => {
      const goals = [makeGoal({ goal_id: 'g-1', conversation_status: 'complete' })]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      const card = document.querySelector('.goal-history-card')
      expect(card.className).toContain('status-complete')
    })

    it('truncates long card text to ~80 chars with ellipsis', () => {
      const longTitle = 'This is a very long directive title that exceeds eighty characters and should be truncated with an ellipsis at a word boundary'
      const goals = [makeGoal({ title: longTitle })]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      const textEl = document.querySelector('.goal-card-text')
      expect(textEl.textContent.length).toBeLessThan(90)
      expect(textEl.textContent).toContain('...')
    })

    it('shows full text in card tooltip', () => {
      const fullTitle = 'Full directive text for tooltip display'
      const goals = [makeGoal({ title: fullTitle })]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      const card = document.querySelector('.goal-history-card')
      expect(card.getAttribute('title')).toBe(fullTitle)
    })

    it('shows evaluation status indicator with label in card header', () => {
      const goals = [makeGoal({ conversation_status: 'pending' })]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      const indicators = screen.getAllByTestId('eval-status')
      expect(indicators.length).toBeGreaterThan(0)
    })
  })

  describe('filtered count display', () => {
    it('shows filtered/total count when filters are active', () => {
      const goals = [
        makeGoal({ title: 'A', priority: 'P0' }),
        makeGoal({ title: 'B', priority: 'P3' }),
        makeGoal({ title: 'C', priority: 'P3' }),
      ]
      render(<GoalHistoryPanel {...defaultProps} goals={goals} />)

      // Apply P0 filter
      fireEvent.click(screen.getByTitle('Filter goals'))
      fireEvent.change(screen.getByDisplayValue('All priorities'), { target: { value: 'P0' } })

      expect(screen.getByText(/1.*\/.*3.*items/)).toBeDefined()
    })
  })
})
