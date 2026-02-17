import { useState, useEffect, useCallback } from 'react'
import { Activity, CheckCircle2, PlayCircle, XCircle, GitBranch, GitMerge, UserPlus } from 'lucide-react'
import { getProjectActivity } from '../../api/projects'
import './Projects.css'

function formatRelativeTime(dateString) {
  if (!dateString) return 'Unknown'

  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now - date
  const diffMinutes = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffMinutes < 1) return 'just now'
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`

  return date.toLocaleDateString()
}

function ActivityIndicatorLarge({ indicator }) {
  const colorMap = {
    green: 'var(--status-online)',
    yellow: 'var(--status-degraded)',
    red: 'var(--status-offline)',
    gray: 'var(--text-muted)'
  }

  const labelMap = {
    green: 'Active',
    yellow: 'Moderate',
    red: 'Stale',
    gray: 'No activity'
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <span
        className="activity-indicator"
        style={{ backgroundColor: colorMap[indicator] || colorMap.gray }}
      />
      <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-muted)' }}>
        {labelMap[indicator] || 'Unknown'}
      </span>
    </div>
  )
}

function EventIcon({ eventType }) {
  const iconMap = {
    work_created: PlayCircle,
    work_started: Activity,
    work_completed: CheckCircle2,
    work_failed: XCircle,
    branch_created: GitBranch,
    branch_merged: GitMerge,
    compute_assigned: UserPlus
  }

  const Icon = iconMap[eventType] || Activity
  return <Icon size={14} className="activity-event-icon" />
}

function ProjectActivity({ projectId }) {
  const [activity, setActivity] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadActivity = useCallback(async () => {
    if (!projectId) return

    try {
      setLoading(true)
      const data = await getProjectActivity(projectId, 10)
      setActivity(data)
      setError(null)
    } catch (err) {
      console.error('Failed to load activity:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    loadActivity()
    // Poll for updates every 30 seconds
    const interval = setInterval(loadActivity, 30000)
    return () => clearInterval(interval)
  }, [loadActivity])

  if (loading && !activity) {
    return (
      <div className="activity-summary">
        <div className="activity-summary-header">
          <Activity size={16} />
          <span>Activity</span>
        </div>
        <div style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-sm)' }}>
          Loading...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="activity-summary">
        <div className="activity-summary-header">
          <Activity size={16} />
          <span>Activity</span>
        </div>
        <div style={{ color: 'var(--status-offline)', fontSize: 'var(--font-size-sm)' }}>
          Failed to load activity
        </div>
      </div>
    )
  }

  const summary = activity?.activity_summary
  const events = activity?.recent_events || []

  return (
    <div className="activity-summary">
      <div className="activity-summary-header">
        <Activity size={16} />
        <span>Activity</span>
        {summary && <ActivityIndicatorLarge indicator={summary.indicator} />}
      </div>

      {summary && (
        <div className="activity-stats">
          <div className="activity-stat">
            <span className="activity-stat-value">{summary.active_work_items}</span>
            <span className="activity-stat-label">Active</span>
          </div>
          <div className="activity-stat">
            <span className="activity-stat-value">{summary.completed_today}</span>
            <span className="activity-stat-label">Today</span>
          </div>
          <div className="activity-stat">
            <span className="activity-stat-value">{summary.completed_week}</span>
            <span className="activity-stat-label">This Week</span>
          </div>
        </div>
      )}

      {summary?.last_activity_at && (
        <div style={{
          fontSize: 'var(--font-size-sm)',
          color: 'var(--text-muted)',
          marginBottom: events.length > 0 ? 'var(--space-md)' : 0
        }}>
          Last activity: {formatRelativeTime(summary.last_activity_at)}
        </div>
      )}

      {events.length > 0 && (
        <>
          <div style={{
            fontSize: 'var(--font-size-xs)',
            fontWeight: 500,
            color: 'var(--text-muted)',
            marginBottom: 'var(--space-sm)',
            marginTop: 'var(--space-md)'
          }}>
            Recent Events
          </div>
          <div className="activity-events">
            {events.map((event) => (
              <div key={event.event_id} className="activity-event">
                <EventIcon eventType={event.event_type} />
                <div className="activity-event-content">
                  <div className="activity-event-description">{event.description}</div>
                  <div className="activity-event-time">
                    {formatRelativeTime(event.timestamp)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {events.length === 0 && !summary?.last_activity_at && (
        <div style={{
          color: 'var(--text-muted)',
          fontSize: 'var(--font-size-sm)',
          textAlign: 'center',
          padding: 'var(--space-md)'
        }}>
          No activity recorded yet
        </div>
      )}
    </div>
  )
}

export default ProjectActivity
