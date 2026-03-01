import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import BucketBadges from './BucketBadges'

describe('BucketBadges', () => {
  it('returns null when entries is null', () => {
    const { container } = render(<BucketBadges entries={null} />)
    expect(container.innerHTML).toBe('')
  })

  it('returns null when entries is empty', () => {
    const { container } = render(<BucketBadges entries={[]} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders a single bucket badge', () => {
    const entries = [
      { name: 'Critical', description: 'Critical fixes', rank: 1, bucket_id: 'b1' },
    ]
    render(<BucketBadges entries={entries} />)
    expect(screen.getByText('Critical')).toBeDefined()
  })

  it('renders up to two badges sorted by rank', () => {
    const entries = [
      { name: 'Low', description: '', rank: 3, bucket_id: 'b3' },
      { name: 'High', description: '', rank: 1, bucket_id: 'b1' },
    ]
    render(<BucketBadges entries={entries} />)
    expect(screen.getByText('High')).toBeDefined()
    expect(screen.getByText('Low')).toBeDefined()
  })

  it('shows overflow count when more than 2 entries', () => {
    const entries = [
      { name: 'A', description: '', rank: 1, bucket_id: 'b1' },
      { name: 'B', description: '', rank: 2, bucket_id: 'b2' },
      { name: 'C', description: '', rank: 3, bucket_id: 'b3' },
    ]
    render(<BucketBadges entries={entries} />)
    expect(screen.getByText('+1')).toBeDefined()
  })

  it('applies rank-based CSS classes', () => {
    const entries = [
      { name: 'Rank1', description: '', rank: 1, bucket_id: 'b1' },
    ]
    render(<BucketBadges entries={entries} />)
    const badge = screen.getByText('Rank1')
    expect(badge.className).toContain('bucket-badge-rank-1')
  })

  it('caps rank class at 3', () => {
    const entries = [
      { name: 'Rank5', description: '', rank: 5, bucket_id: 'b5' },
    ]
    render(<BucketBadges entries={entries} />)
    const badge = screen.getByText('Rank5')
    expect(badge.className).toContain('bucket-badge-rank-3')
  })

  it('uses description as title attribute', () => {
    const entries = [
      { name: 'Test', description: 'Detailed description', rank: 1, bucket_id: 'b1' },
    ]
    render(<BucketBadges entries={entries} />)
    const badge = screen.getByText('Test')
    expect(badge.getAttribute('title')).toBe('Detailed description')
  })

  it('falls back to name as title when no description', () => {
    const entries = [
      { name: 'Test', description: '', rank: 1, bucket_id: 'b1' },
    ]
    render(<BucketBadges entries={entries} />)
    const badge = screen.getByText('Test')
    expect(badge.getAttribute('title')).toBe('Test')
  })
})
