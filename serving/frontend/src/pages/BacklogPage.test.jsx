import { describe, it, expect } from 'vitest'
import { formatIssueId } from './BacklogPage'

describe('formatIssueId', () => {
  it('strips issue_ prefix and returns first 8 chars of hash', () => {
    expect(formatIssueId('issue_a9bc15c574b8')).toBe('a9bc15c5')
  })

  it('returns first 8 chars when no issue_ prefix', () => {
    expect(formatIssueId('a9bc15c574b8deadbeef')).toBe('a9bc15c5')
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

  it('handles short IDs without truncation issues', () => {
    expect(formatIssueId('issue_abc')).toBe('abc')
  })

  it('handles ID that is exactly the prefix with no hash', () => {
    expect(formatIssueId('issue_')).toBe('')
  })
})
