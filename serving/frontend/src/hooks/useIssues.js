import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { getAllIssues } from '../api/workmap'
import useObservability from './useObservability'

function useIssues(options = {}) {
  const { pollInterval = 5000, filters = {}, useWebSocket = true, key = 0 } = options

  const [items, setItems] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const lastEventRef = useRef(null)

  // Serialize filters for stable dependency comparison
  const filtersKey = useMemo(() => JSON.stringify(filters), [filters])

  // WebSocket connection for real-time updates
  const { connected, latestEvent } = useObservability({ autoConnect: useWebSocket })

  const load = useCallback(async () => {
    try {
      const currentFilters = JSON.parse(filtersKey)
      const response = await getAllIssues(currentFilters)
      const issueItems = response.items || []
      setItems(issueItems)
      setStats({
        total: response.total || 0,
        by_status: response.by_status || {},
        by_priority: response.by_priority || {},
        blocked_count: (response.by_status || {}).blocked || 0
      })
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filtersKey])

  // Reload when filters or key changes
  useEffect(() => {
    setLoading(true)
    load()
  }, [load, key])

  const refresh = useCallback(() => {
    load()
  }, [load])

  // Handle WebSocket events for real-time updates
  useEffect(() => {
    if (latestEvent && latestEvent !== lastEventRef.current) {
      lastEventRef.current = latestEvent
      const eventType = latestEvent.type

      // Refresh on issue-related events
      if (eventType === 'work_status_change' ||
          eventType === 'issue_created' ||
          eventType === 'issue_updated') {
        refresh()
      }
    }
  }, [latestEvent, refresh])

  // Fallback polling when WebSocket is disconnected
  useEffect(() => {
    if ((!useWebSocket || !connected) && pollInterval > 0) {
      const interval = setInterval(load, pollInterval)
      return () => clearInterval(interval)
    }
  }, [load, pollInterval, connected, useWebSocket])

  return { items, stats, loading, error, refresh, connected }
}

export default useIssues
