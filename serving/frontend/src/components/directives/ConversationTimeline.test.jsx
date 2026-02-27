import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ConversationTimeline from './ConversationTimeline'
import { MSG_TYPES } from '../../hooks/useConversation'

// Mock scrollIntoView
Element.prototype.scrollIntoView = vi.fn()

function makeMsg(type, content, meta = {}) {
  return { id: Math.random(), type, content, timestamp: '2025-01-15T10:30:00Z', ...meta }
}

describe('ConversationTimeline', () => {
  const defaultProps = {
    messages: [],
    pendingDirective: null,
    applying: false,
    onApply: vi.fn(),
    onReject: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null when messages are empty', () => {
    const { container } = render(<ConversationTimeline {...defaultProps} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders user message with text and time', () => {
    const messages = [makeMsg(MSG_TYPES.USER, 'Hello world')]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    expect(screen.getByText('Hello world')).toBeDefined()
    // Time formatting is locale-dependent, just check the time element exists
    const timeEl = document.querySelector('.conv-msg-time')
    expect(timeEl).not.toBeNull()
    expect(timeEl.textContent.length).toBeGreaterThan(0)
  })

  it('renders thinking message with spinner text', () => {
    const messages = [makeMsg(MSG_TYPES.THINKING, 'Interpreting directive...')]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    expect(screen.getByText('Interpreting directive...')).toBeDefined()
  })

  it('renders goal created message as brief confirmation without duplicating title', () => {
    const messages = [
      makeMsg(MSG_TYPES.GOAL_CREATED, 'Created: Test goal', {
        goal: { title: 'Test goal', priority: 'P1' },
      }),
    ]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    expect(screen.getByText('New Work Created')).toBeDefined()
    // Title and priority should NOT be rendered (they're shown in the goal header)
    expect(screen.queryByText('Test goal')).toBeNull()
    expect(screen.queryByText('P1')).toBeNull()
  })

  it('renders goal processing message with stage label and stepper', () => {
    const messages = [makeMsg(MSG_TYPES.GOAL_PROCESSING, 'Processing', {
      stage: 'decomposing',
      startedAt: new Date().toISOString(),
    })]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    expect(screen.getByText('Decomposing goal...')).toBeDefined()
    // Stepper shows all stage names (without trailing "...")
    expect(screen.getByText('Queuing work')).toBeDefined()
    expect(screen.getByText('Decomposing goal')).toBeDefined()
    expect(screen.getByText('Characterizing work items')).toBeDefined()
    expect(screen.getByText('Creating backlog items')).toBeDefined()
  })

  it('renders goal processing with fallback label for unknown stage', () => {
    const messages = [makeMsg(MSG_TYPES.GOAL_PROCESSING, 'Processing', { stage: 'unknown' })]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    expect(screen.getByText('Processing...')).toBeDefined()
  })

  it('renders characterizing stage correctly', () => {
    const messages = [makeMsg(MSG_TYPES.GOAL_PROCESSING, 'Processing', {
      stage: 'characterizing',
      startedAt: new Date().toISOString(),
    })]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    expect(screen.getByText('Characterizing work items...')).toBeDefined()
  })

  it('shows elapsed time when startedAt is provided', () => {
    const messages = [makeMsg(MSG_TYPES.GOAL_PROCESSING, 'Processing', {
      stage: 'decomposing',
      startedAt: new Date().toISOString(),
    })]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    const elapsed = document.querySelector('.conv-elapsed')
    expect(elapsed).not.toBeNull()
    expect(elapsed.textContent).toMatch(/^\d+s$/)
  })

  it('marks completed stages as done in stepper', () => {
    const messages = [makeMsg(MSG_TYPES.GOAL_PROCESSING, 'Processing', {
      stage: 'creating_issues',
      startedAt: new Date().toISOString(),
    })]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    const steps = document.querySelectorAll('.conv-stage-step')
    expect(steps.length).toBe(4)
    // First 3 stages should be done (queued, decomposing, characterizing)
    expect(steps[0].classList.contains('done')).toBe(true)
    expect(steps[1].classList.contains('done')).toBe(true)
    expect(steps[2].classList.contains('done')).toBe(true)
    // Last stage is active
    expect(steps[3].classList.contains('active')).toBe(true)
  })

  it('shows stalled warning when processing is stalled', () => {
    const messages = [makeMsg(MSG_TYPES.GOAL_PROCESSING, 'Processing', {
      stage: 'decomposing',
      startedAt: new Date().toISOString(),
      isStalled: true,
    })]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    expect(screen.getByText('Decomposing goal...')).toBeDefined()
    expect(screen.getByText('This is taking longer than expected...')).toBeDefined()
  })

  it('shows timeout state with retry button when timed out', () => {
    const onRetry = vi.fn()
    const messages = [makeMsg(MSG_TYPES.GOAL_PROCESSING, 'Processing', {
      stage: 'decomposing',
      isTimedOut: true,
    })]
    render(<ConversationTimeline {...defaultProps} messages={messages} onRetry={onRetry} />)

    expect(screen.getByText('Processing Timed Out')).toBeDefined()
    expect(screen.getByText(/Processing has not completed after 5 minutes/)).toBeDefined()
    expect(screen.getByText('Retry')).toBeDefined()
  })

  it('calls onRetry when retry button is clicked', () => {
    const onRetry = vi.fn()
    const messages = [makeMsg(MSG_TYPES.GOAL_PROCESSING, 'Processing', {
      stage: 'decomposing',
      isTimedOut: true,
    })]
    render(<ConversationTimeline {...defaultProps} messages={messages} onRetry={onRetry} />)

    fireEvent.click(screen.getByText('Retry'))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('does not show stalled warning when not stalled', () => {
    const messages = [makeMsg(MSG_TYPES.GOAL_PROCESSING, 'Processing', {
      stage: 'decomposing',
      startedAt: new Date().toISOString(),
      isStalled: false,
    })]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    expect(screen.queryByText('This is taking longer than expected...')).toBeNull()
  })

  it('renders goal complete message with issues list', () => {
    const messages = [
      makeMsg(MSG_TYPES.GOAL_COMPLETE, 'Work items created', {
        result: {
          issues_created: [
            { issue_id: 'i-1', title: 'Fix login bug', priority: 'P0' },
            { issue_id: 'i-2', title: 'Add tests' },
          ],
        },
      }),
    ]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    expect(screen.getByText('Work Items Created')).toBeDefined()
    expect(screen.getByText('Fix login bug')).toBeDefined()
    expect(screen.getByText('P0')).toBeDefined()
    expect(screen.getByText('Add tests')).toBeDefined()
  })

  it('renders directive preview with weight changes', () => {
    const directive = {
      directive_id: 'd-1',
      interpretation: {
        detected_intent: 'priority_shift',
        summary: 'Focus on testing',
        weight_adjustments: [
          { category: 'domain', key: 'testing', current_weight: 0.3, proposed_weight: 0.8 },
        ],
      },
    }
    const messages = [
      makeMsg(MSG_TYPES.DIRECTIVE_PREVIEW, 'Here is what I understood:', { directive }),
    ]
    render(
      <ConversationTimeline
        {...defaultProps}
        messages={messages}
        pendingDirective={directive}
      />
    )

    expect(screen.getByText('Focus on testing')).toBeDefined()
    expect(screen.getByText('Weight Changes')).toBeDefined()
    expect(screen.getByText('domain/testing')).toBeDefined()
    expect(screen.getByText('30%')).toBeDefined()
    expect(screen.getByText('80%')).toBeDefined()
  })

  it('renders directive preview with policy changes', () => {
    const directive = {
      directive_id: 'd-2',
      interpretation: {
        detected_intent: 'policy_change',
        summary: 'Add constraint',
        policy_adjustments: [
          { action: 'add', rule_name: 'No weekend deploys', rule_description: 'Block deploys on weekends' },
        ],
      },
    }
    const messages = [
      makeMsg(MSG_TYPES.DIRECTIVE_PREVIEW, 'Directive:', { directive }),
    ]
    render(
      <ConversationTimeline
        {...defaultProps}
        messages={messages}
        pendingDirective={directive}
      />
    )

    expect(screen.getByText('Policy Changes')).toBeDefined()
    expect(screen.getByText('No weekend deploys')).toBeDefined()
    expect(screen.getByText('Block deploys on weekends')).toBeDefined()
  })

  it('shows apply/reject buttons when directive is pending', () => {
    const directive = {
      directive_id: 'd-1',
      interpretation: { detected_intent: 'test', summary: 'test' },
    }
    const messages = [
      makeMsg(MSG_TYPES.DIRECTIVE_PREVIEW, 'Preview:', { directive }),
    ]
    render(
      <ConversationTimeline
        {...defaultProps}
        messages={messages}
        pendingDirective={directive}
      />
    )

    expect(screen.getByText('Apply')).toBeDefined()
    expect(screen.getByText('Reject')).toBeDefined()
  })

  it('disables buttons while applying', () => {
    const directive = {
      directive_id: 'd-1',
      interpretation: { detected_intent: 'test', summary: 'test' },
    }
    const messages = [
      makeMsg(MSG_TYPES.DIRECTIVE_PREVIEW, 'Preview:', { directive }),
    ]
    render(
      <ConversationTimeline
        {...defaultProps}
        messages={messages}
        pendingDirective={directive}
        applying={true}
      />
    )

    expect(screen.getByText('Applying...')).toBeDefined()
    const buttons = screen.getAllByRole('button')
    buttons.forEach(btn => {
      expect(btn.disabled).toBe(true)
    })
  })

  it('calls onApply when Apply button clicked', () => {
    const onApply = vi.fn()
    const directive = {
      directive_id: 'd-1',
      interpretation: { detected_intent: 'test', summary: 'test' },
    }
    const messages = [
      makeMsg(MSG_TYPES.DIRECTIVE_PREVIEW, 'Preview:', { directive }),
    ]
    render(
      <ConversationTimeline
        {...defaultProps}
        messages={messages}
        pendingDirective={directive}
        onApply={onApply}
      />
    )

    fireEvent.click(screen.getByText('Apply'))
    expect(onApply).toHaveBeenCalledTimes(1)
  })

  it('calls onReject when Reject button clicked', () => {
    const onReject = vi.fn()
    const directive = {
      directive_id: 'd-1',
      interpretation: { detected_intent: 'test', summary: 'test' },
    }
    const messages = [
      makeMsg(MSG_TYPES.DIRECTIVE_PREVIEW, 'Preview:', { directive }),
    ]
    render(
      <ConversationTimeline
        {...defaultProps}
        messages={messages}
        pendingDirective={directive}
        onReject={onReject}
      />
    )

    fireEvent.click(screen.getByText('Reject'))
    expect(onReject).toHaveBeenCalledTimes(1)
  })

  it('does not show apply/reject when directive is not pending', () => {
    const directive = {
      directive_id: 'd-1',
      interpretation: { detected_intent: 'test', summary: 'test' },
    }
    const messages = [
      makeMsg(MSG_TYPES.DIRECTIVE_PREVIEW, 'Preview:', { directive }),
    ]
    render(
      <ConversationTimeline
        {...defaultProps}
        messages={messages}
        pendingDirective={null}
      />
    )

    expect(screen.queryByText('Apply')).toBeNull()
    expect(screen.queryByText('Reject')).toBeNull()
  })

  it('renders directive applied message', () => {
    const messages = [
      makeMsg(MSG_TYPES.DIRECTIVE_APPLIED, 'Changes applied', {
        directive: { interpretation: { detected_intent: 'priority_shift', summary: 'Focus testing' } },
      }),
    ]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    expect(screen.getByText('Changes Applied')).toBeDefined()
    expect(screen.getByText('Focus testing')).toBeDefined()
  })

  it('renders directive rejected message', () => {
    const messages = [makeMsg(MSG_TYPES.DIRECTIVE_REJECTED, 'Changes rejected')]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    expect(screen.getByText('Changes Rejected')).toBeDefined()
  })

  it('renders error message', () => {
    const messages = [makeMsg(MSG_TYPES.ERROR, 'Something went wrong')]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    expect(screen.getByText('Something went wrong')).toBeDefined()
  })

  it('renders multiple message types in sequence', () => {
    const messages = [
      makeMsg(MSG_TYPES.USER, 'Build feature'),
      makeMsg(MSG_TYPES.GOAL_CREATED, 'Created', { goal: { title: 'Feature', priority: 'P2' } }),
      makeMsg(MSG_TYPES.GOAL_COMPLETE, 'Done', { result: { issues_created: [] } }),
    ]
    render(<ConversationTimeline {...defaultProps} messages={messages} />)

    expect(screen.getByText('Build feature')).toBeDefined()
    expect(screen.getByText('New Work Created')).toBeDefined()
    expect(screen.getByText('Work Items Created')).toBeDefined()
  })
})
