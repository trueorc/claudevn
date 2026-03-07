import { useState, useEffect, useCallback, useRef } from 'react'
import { getTimingDashboard } from '../api/timing'
import useObservability from './useObservability'

function useTiming(projectId, options = {}) {
  const { pollInterval = 10000, limit = 20, useWebSocket = true } = options

  const [dashboard, setDashboard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const lastEventRef = useRef(null)

  // WebSocket connection for real-time updates
  const { connected, latestEvent } = useObservability({ autoConnect: useWebSocket })

  const load = useCallback(async () => {
    if (!projectId) {
      setDashboard(null)
      setLoading(false)
      return
    }
    try {
      const data = await getTimingDashboard(limit, projectId)
      setDashboard(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [limit, projectId])

  const refresh = useCallback(() => {
    load()
  }, [load])

  // Initial fetch
  useEffect(() => {
    load()
  }, [load])

  // Handle WebSocket events for real-time updates
  useEffect(() => {
    if (latestEvent && latestEvent !== lastEventRef.current) {
      lastEventRef.current = latestEvent
      const eventType = latestEvent.type

      if (eventType === 'work_status_change' ||
          eventType === 'activity_state_change' ||
          eventType === 'compute_registered' ||
          eventType === 'compute_deregistered') {
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

  return {
    dashboard,
    workItems: dashboard?.work_items || [],
    aggregates: dashboard?.aggregates || [],
    totalWorkItems: dashboard?.total_work_items || 0,
    projectSummary: dashboard?.project_summary || null,
    loading,
    error,
    refresh
  }
}

export { useTiming }
export default useTiming
