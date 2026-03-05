import { useMemo } from 'react'

const STATUS_LABELS = {
  new: 'created',
  pending: 'moved to pending',
  ready: 'marked ready',
  in_progress: 'started',
  in_review: 'moved to review',
  testing: 'moved to testing',
  done: 'completed',
  blocked: 'blocked',
  cancelled: 'cancelled',
}

function formatRelativeTime(dateStr) {
  if (!dateStr) return ''

  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return ''

  const now = Date.now()
  const diffMs = now - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)

  if (diffSec < 60) return 'just now'

  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`

  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`

  const diffDays = Math.floor(diffHr / 24)
  if (diffDays === 1) return '1d ago'
  if (diffDays < 7) return `${diffDays}d ago`

  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function useRecentActivity({ items = [], maxEvents = 10 } = {}) {
  const events = useMemo(() => {
    if (!items || items.length === 0) return []

    const derived = items
      .filter(item => item.updated_at)
      .map(item => {
        const statusLabel = STATUS_LABELS[item.status] || item.status
        const title = item.title || item.name || `Issue ${item.issue_id}`
        // Truncate long titles to keep single-line layout clean
        const shortTitle = title.length > 60 ? title.slice(0, 57) + '...' : title

        return {
          id: item.issue_id,
          description: `"${shortTitle}" ${statusLabel}`,
          timestamp: item.updated_at,
          relativeTime: formatRelativeTime(item.updated_at),
        }
      })

    // Sort most recent first, take top N
    derived.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))

    return derived.slice(0, maxEvents)
  }, [items, maxEvents])

  return { events }
}

export default useRecentActivity
