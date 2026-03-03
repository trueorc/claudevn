import { describe, it, expect } from 'vitest'
import { formatIssueId } from './BacklogPage'

describe('formatIssueId', () => {
  it('returns the full issue ID unchanged', () => {
    expect(formatIssueId('issue_a9bc15c574b8')).toBe('issue_a9bc15c574b8')
  })

  it('returns full ID when no issue_ prefix', () => {
    expect(formatIssueId('a9bc15c574b8deadbeef')).toBe('a9bc15c574b8deadbeef')
  })

  it('returns empty string for null', () => {
    expect(formatIssueId(null)).toBe('')
  })

  it('returns empty string for undefined', () => {
    expect(formatIssueId(undefined)).toBe('')
  })

  it('returns empty string for empty string', () => {
    expect(formatIssueId('')).toBe('')
  })

  it('returns full ID including prefix for short IDs', () => {
    expect(formatIssueId('issue_abc')).toBe('issue_abc')
  })

  it('returns issue_ prefix as-is', () => {
    expect(formatIssueId('issue_')).toBe('issue_')
  })
})
