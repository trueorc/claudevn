import { describe, it, expect } from 'vitest'
import { formatDuration, cleanToolName, classifyWorkItems, sumEntryDurations, LONG_RUNNING_THRESHOLD_MS } from './TimingPage'

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

describe('sumEntryDurations', () => {
  it('returns 0 for empty array', () => {
    expect(sumEntryDurations([])).toBe(0)
  })

  it('sums all entry durations excluding total_wall_time', () => {
    const items = [
      {
        entries: [
          { phase: 'mcp_tool_call', duration_ms: 100 },
          { phase: 'mcp_tool_call', duration_ms: 200 },
          { phase: 'total_wall_time', duration_ms: 5000 },
        ]
      },
      {
        entries: [
          { phase: 'sdk_launch', duration_ms: 300 },
        ]
      }
    ]
    expect(sumEntryDurations(items)).toBe(600)
  })

  it('handles entries with null duration_ms', () => {
    const items = [
      {
        entries: [
          { phase: 'mcp_tool_call', duration_ms: null },
          { phase: 'mcp_tool_call', duration_ms: 100 },
        ]
      }
    ]
    expect(sumEntryDurations(items)).toBe(100)
  })
})

describe('classifyWorkItems', () => {
  const makeItem = (workId, { issueId, issueTitle, directiveId, directiveTitle, createdAt } = {}) => ({
    work_id: workId,
    instance_id: 'compute-1',
    issue_id: issueId || null,
    issue_title: issueTitle || null,
    directive_id: directiveId || null,
    directive_title: directiveTitle || null,
    created_at: createdAt || '2024-01-01T00:00:00Z',
    entries: [
      { phase: 'mcp_tool_call', duration_ms: 100, start: '2024-01-01T00:00:00Z', metadata: {} }
    ]
  })

  it('returns empty tiers for empty input', () => {
    const result = classifyWorkItems([])
    expect(result.directives).toEqual([])
    expect(result.issues).toEqual([])
    expect(result.unassigned).toEqual([])
  })

  it('classifies items with issue_id into issues tier', () => {
    const items = [
      makeItem('w1', { issueId: 'issue-42', issueTitle: 'Fix bug' }),
      makeItem('w2', { issueId: 'issue-42', issueTitle: 'Fix bug' }),
      makeItem('w3', { issueId: 'issue-43', issueTitle: 'Add feature' }),
    ]

    const result = classifyWorkItems(items)
    expect(result.issues).toHaveLength(2)
    expect(result.directives).toHaveLength(0)
    expect(result.unassigned).toHaveLength(0)

    const issue42 = result.issues.find(g => g.key === 'issue-42')
    expect(issue42.items).toHaveLength(2)
    expect(issue42.label).toBe('Fix bug')
  })

  it('classifies items with directive_id into directives tier', () => {
    const items = [
      makeItem('decomp-abc', { directiveId: 'dir-1', directiveTitle: 'Build auth' }),
      makeItem('char-def', { directiveId: 'dir-1', directiveTitle: 'Build auth' }),
    ]

    const result = classifyWorkItems(items)
    expect(result.directives).toHaveLength(1)
    expect(result.directives[0].items).toHaveLength(2)
    expect(result.directives[0].label).toBe('Build auth')
    expect(result.issues).toHaveLength(0)
    expect(result.unassigned).toHaveLength(0)
  })

  it('classifies items without issue or directive into unassigned tier', () => {
    const items = [
      makeItem('w1'),
      makeItem('w2'),
    ]

    const result = classifyWorkItems(items)
    expect(result.unassigned).toHaveLength(2)
    expect(result.directives).toHaveLength(0)
    expect(result.issues).toHaveLength(0)
  })

  it('issue_id takes precedence over directive_id for classification', () => {
    // An item with both issue_id and directive_id goes to the issues tier
    const items = [
      makeItem('w1', { issueId: 'issue-42', issueTitle: 'Fix', directiveId: 'dir-1' }),
    ]

    const result = classifyWorkItems(items)
    expect(result.issues).toHaveLength(1)
    expect(result.directives).toHaveLength(0)
  })

  it('sorts groups by most recent work item', () => {
    const items = [
      makeItem('w1', { issueId: 'issue-42', issueTitle: 'Old', createdAt: '2024-01-01T01:00:00Z' }),
      makeItem('w2', { issueId: 'issue-43', issueTitle: 'New', createdAt: '2024-01-01T03:00:00Z' }),
    ]

    const result = classifyWorkItems(items)
    expect(result.issues[0].label).toBe('New')
    expect(result.issues[1].label).toBe('Old')
  })
})
