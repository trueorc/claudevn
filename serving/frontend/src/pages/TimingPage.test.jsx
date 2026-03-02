import { describe, it, expect } from 'vitest'
import { formatDuration, cleanToolName, groupByTier, LONG_RUNNING_THRESHOLD_MS } from './TimingPage'

describe('formatDuration', () => {
  it('returns dash for null/undefined', () => {
    expect(formatDuration(null)).toBe('-')
    expect(formatDuration(undefined)).toBe('-')
  })

  it('formats milliseconds', () => {
    expect(formatDuration(0)).toBe('0ms')
    expect(formatDuration(500)).toBe('500ms')
    expect(formatDuration(999)).toBe('999ms')
  })

  it('formats seconds', () => {
    expect(formatDuration(1000)).toBe('1.0s')
    expect(formatDuration(5300)).toBe('5.3s')
    expect(formatDuration(59999)).toBe('60.0s')
  })

  it('formats minutes', () => {
    expect(formatDuration(60000)).toBe('1.0m')
    expect(formatDuration(90000)).toBe('1.5m')
    expect(formatDuration(1862000)).toBe('31.0m')
  })
})

describe('cleanToolName', () => {
  it('strips claudevn_ prefix', () => {
    expect(cleanToolName('claudevn_get_context')).toBe('get_context')
    expect(cleanToolName('claudevn_request_review')).toBe('request_review')
  })

  it('leaves names without prefix unchanged', () => {
    expect(cleanToolName('get_context')).toBe('get_context')
    expect(cleanToolName('some_tool')).toBe('some_tool')
  })

  it('handles null/undefined', () => {
    expect(cleanToolName(null)).toBe(null)
    expect(cleanToolName(undefined)).toBe(undefined)
  })

  it('handles empty string', () => {
    expect(cleanToolName('')).toBe('')
  })
})

describe('LONG_RUNNING_THRESHOLD_MS', () => {
  it('is 90 seconds', () => {
    expect(LONG_RUNNING_THRESHOLD_MS).toBe(90000)
  })
})

describe('groupByTier', () => {
  const makeItem = (workId, opts = {}) => ({
    work_id: workId,
    instance_id: 'compute-1',
    issue_id: opts.issueId || null,
    issue_title: opts.issueTitle || null,
    goal_id: opts.goalId || null,
    directive_id: opts.directiveId || null,
    directive_text: opts.directiveText || null,
    created_at: opts.createdAt || '2024-01-01T00:00:00Z',
    entries: [
      { phase: 'mcp_tool_call', duration_ms: 100, start: '2024-01-01T00:00:00Z', metadata: {} }
    ]
  })

  it('returns empty tiers for empty input', () => {
    const { directives, issues, untrackedGroups } = groupByTier([])
    expect(directives).toEqual([])
    expect(issues).toEqual([])
    expect(untrackedGroups).toEqual([])
  })

  it('groups items with directive_id into directives tier', () => {
    const items = [
      makeItem('w1', { directiveId: 'd-1', directiveText: 'Build feature', issueId: 'i-1', issueTitle: 'Task 1' }),
      makeItem('w2', { directiveId: 'd-1', directiveText: 'Build feature', issueId: 'i-2', issueTitle: 'Task 2' }),
    ]

    const { directives, issues, untrackedGroups } = groupByTier(items)
    expect(directives).toHaveLength(1)
    expect(directives[0].directiveId).toBe('d-1')
    expect(directives[0].directiveText).toBe('Build feature')
    expect(directives[0].issueGroups).toHaveLength(2)
    expect(issues).toHaveLength(0)
    expect(untrackedGroups).toHaveLength(0)
  })

  it('groups items with issue_id but no directive into issues tier', () => {
    const items = [
      makeItem('w1', { issueId: 'i-1', issueTitle: 'Fix bug' }),
      makeItem('w2', { issueId: 'i-1', issueTitle: 'Fix bug' }),
      makeItem('w3', { issueId: 'i-2', issueTitle: 'Add test' }),
    ]

    const { directives, issues, untrackedGroups } = groupByTier(items)
    expect(directives).toHaveLength(0)
    expect(issues).toHaveLength(2)
    expect(issues.find(g => g.issueId === 'i-1').items).toHaveLength(2)
    expect(untrackedGroups).toHaveLength(0)
  })

  it('puts items with no issue or directive into untracked tier', () => {
    const items = [
      makeItem('w1'),
      makeItem('w2'),
    ]

    const { directives, issues, untrackedGroups } = groupByTier(items)
    expect(directives).toHaveLength(0)
    expect(issues).toHaveLength(0)
    expect(untrackedGroups).toHaveLength(2)
  })

  it('sorts directives by most recent activity', () => {
    const items = [
      makeItem('w1', { directiveId: 'd-old', issueId: 'i-1', createdAt: '2024-01-01T01:00:00Z' }),
      makeItem('w2', { directiveId: 'd-new', issueId: 'i-2', createdAt: '2024-01-01T03:00:00Z' }),
    ]

    const { directives } = groupByTier(items)
    expect(directives[0].directiveId).toBe('d-new')
    expect(directives[1].directiveId).toBe('d-old')
  })

  it('sorts issues by most recent work item', () => {
    const items = [
      makeItem('w1', { issueId: 'i-old', createdAt: '2024-01-01T01:00:00Z' }),
      makeItem('w2', { issueId: 'i-new', createdAt: '2024-01-01T03:00:00Z' }),
    ]

    const { issues } = groupByTier(items)
    expect(issues[0].issueId).toBe('i-new')
    expect(issues[1].issueId).toBe('i-old')
  })

  it('fills in directive text from any item in the group', () => {
    const items = [
      makeItem('w1', { directiveId: 'd-1', issueId: 'i-1' }),
      makeItem('w2', { directiveId: 'd-1', directiveText: 'Build feature', issueId: 'i-2' }),
    ]

    const { directives } = groupByTier(items)
    expect(directives[0].directiveText).toBe('Build feature')
  })

  it('fills in issue title from any item in the group', () => {
    const items = [
      makeItem('w1', { issueId: 'i-1' }),
      makeItem('w2', { issueId: 'i-1', issueTitle: 'Fix the bug' }),
    ]

    const { issues } = groupByTier(items)
    expect(issues[0].issueTitle).toBe('Fix the bug')
  })

  it('handles mixed tiers correctly', () => {
    const items = [
      makeItem('w1', { directiveId: 'd-1', issueId: 'i-1', issueTitle: 'Task 1' }),
      makeItem('w2', { issueId: 'i-2', issueTitle: 'Standalone' }),
      makeItem('w3'),
    ]

    const { directives, issues, untrackedGroups } = groupByTier(items)
    expect(directives).toHaveLength(1)
    expect(issues).toHaveLength(1)
    expect(untrackedGroups).toHaveLength(1)
  })
})
