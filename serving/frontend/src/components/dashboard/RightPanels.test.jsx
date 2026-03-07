import { describe, it, expect } from 'vitest'
import { computeTimingInsights } from './RightPanels'

describe('computeTimingInsights', () => {
  it('returns null for null/undefined/empty input', () => {
    expect(computeTimingInsights(null)).toBeNull()
    expect(computeTimingInsights(undefined)).toBeNull()
    expect(computeTimingInsights([])).toBeNull()
  })

  it('computes total project time from total_wall_time entries', () => {
    const workItems = [
      {
        entries: [
          { phase: 'total_wall_time', duration_ms: 10000 },
          { phase: 'sdk_launch', duration_ms: 500 },
        ],
      },
      {
        entries: [
          { phase: 'total_wall_time', duration_ms: 20000 },
        ],
      },
    ]

    const result = computeTimingInsights(workItems)
    expect(result.totalMs).toBe(30000)
  })

  it('computes average issue completion time', () => {
    const workItems = [
      {
        issue_id: 'issue-1',
        entries: [{ phase: 'total_wall_time', duration_ms: 10000 }],
      },
      {
        issue_id: 'issue-1',
        entries: [{ phase: 'total_wall_time', duration_ms: 20000 }],
      },
      {
        issue_id: 'issue-2',
        entries: [{ phase: 'total_wall_time', duration_ms: 6000 }],
      },
    ]

    const result = computeTimingInsights(workItems)
    // issue-1 total = 30000, issue-2 total = 6000, avg = 18000
    expect(result.avgIssueMs).toBe(18000)
    expect(result.issueCount).toBe(2)
  })

  it('computes average directive completion time', () => {
    const workItems = [
      {
        directive_id: 'dir-1',
        entries: [{ phase: 'total_wall_time', duration_ms: 15000 }],
      },
      {
        directive_id: 'dir-2',
        entries: [{ phase: 'total_wall_time', duration_ms: 9000 }],
      },
    ]

    const result = computeTimingInsights(workItems)
    expect(result.avgDirectiveMs).toBe(12000)
    expect(result.directiveCount).toBe(2)
  })

  it('excludes __system__ directives', () => {
    const workItems = [
      {
        directive_id: '__system__',
        entries: [{ phase: 'total_wall_time', duration_ms: 5000 }],
      },
      {
        directive_id: 'dir-1',
        entries: [{ phase: 'total_wall_time', duration_ms: 8000 }],
      },
    ]

    const result = computeTimingInsights(workItems)
    expect(result.avgDirectiveMs).toBe(8000)
    expect(result.directiveCount).toBe(1)
  })

  it('returns null averages when no issues/directives exist', () => {
    const workItems = [
      {
        entries: [{ phase: 'total_wall_time', duration_ms: 5000 }],
      },
    ]

    const result = computeTimingInsights(workItems)
    expect(result.totalMs).toBe(5000)
    expect(result.avgIssueMs).toBeNull()
    expect(result.avgDirectiveMs).toBeNull()
    expect(result.issueCount).toBe(0)
    expect(result.directiveCount).toBe(0)
  })

  it('handles work items with no total_wall_time entry', () => {
    const workItems = [
      {
        issue_id: 'issue-1',
        entries: [{ phase: 'sdk_launch', duration_ms: 500 }],
      },
    ]

    const result = computeTimingInsights(workItems)
    expect(result.totalMs).toBe(0)
    expect(result.avgIssueMs).toBeNull()
    expect(result.issueCount).toBe(0)
  })

  it('handles work items with null duration_ms', () => {
    const workItems = [
      {
        entries: [{ phase: 'total_wall_time', duration_ms: null }],
      },
    ]

    const result = computeTimingInsights(workItems)
    expect(result.totalMs).toBe(0)
  })

  it('handles missing entries field', () => {
    const workItems = [{ issue_id: 'issue-1' }]

    const result = computeTimingInsights(workItems)
    expect(result.totalMs).toBe(0)
  })
})
