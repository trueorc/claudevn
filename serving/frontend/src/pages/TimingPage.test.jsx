import { describe, it, expect } from 'vitest'
import { formatDuration, cleanToolName, groupByIssue, LONG_RUNNING_THRESHOLD_MS } from './TimingPage'

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

describe('groupByIssue', () => {
  const makeItem = (workId, issueId, issueTitle, createdAt) => ({
    work_id: workId,
    instance_id: 'compute-1',
    issue_id: issueId,
    issue_title: issueTitle,
    created_at: createdAt || '2024-01-01T00:00:00Z',
    entries: [
      { phase: 'mcp_tool_call', duration_ms: 100, start: '2024-01-01T00:00:00Z', metadata: {} }
    ]
  })

  it('returns empty array for empty input', () => {
    expect(groupByIssue([])).toEqual([])
  })

  it('groups work items by issue_id', () => {
    const items = [
      makeItem('w1', 'issue-42', 'Fix bug', '2024-01-01T01:00:00Z'),
      makeItem('w2', 'issue-42', 'Fix bug', '2024-01-01T02:00:00Z'),
      makeItem('w3', 'issue-43', 'Add feature', '2024-01-01T03:00:00Z'),
    ]

    const groups = groupByIssue(items)
    expect(groups).toHaveLength(2)

    const issue42 = groups.find(g => g.issueId === 'issue-42')
    expect(issue42.items).toHaveLength(2)
    expect(issue42.issueTitle).toBe('Fix bug')

    const issue43 = groups.find(g => g.issueId === 'issue-43')
    expect(issue43.items).toHaveLength(1)
  })

  it('creates separate groups for items without issue_id', () => {
    const items = [
      makeItem('w1', null, null, '2024-01-01T01:00:00Z'),
      makeItem('w2', null, null, '2024-01-01T02:00:00Z'),
    ]

    const groups = groupByIssue(items)
    expect(groups).toHaveLength(2)
  })

  it('sorts issues before no-issue items', () => {
    const items = [
      makeItem('w1', null, null, '2024-01-01T03:00:00Z'),
      makeItem('w2', 'issue-42', 'Fix bug', '2024-01-01T01:00:00Z'),
    ]

    const groups = groupByIssue(items)
    expect(groups[0].issueId).toBe('issue-42')
    expect(groups[1].issueId).toBeNull()
  })

  it('sorts issues by most recent work item', () => {
    const items = [
      makeItem('w1', 'issue-42', 'Old issue', '2024-01-01T01:00:00Z'),
      makeItem('w2', 'issue-43', 'New issue', '2024-01-01T03:00:00Z'),
    ]

    const groups = groupByIssue(items)
    expect(groups[0].issueId).toBe('issue-43')
    expect(groups[1].issueId).toBe('issue-42')
  })

  it('fills in issue title from any item in the group', () => {
    const items = [
      makeItem('w1', 'issue-42', null, '2024-01-01T01:00:00Z'),
      makeItem('w2', 'issue-42', 'Fix the bug', '2024-01-01T02:00:00Z'),
    ]

    const groups = groupByIssue(items)
    expect(groups[0].issueTitle).toBe('Fix the bug')
  })
})
