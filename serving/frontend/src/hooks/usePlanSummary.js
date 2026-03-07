import { useState, useCallback, useEffect, useRef } from 'react'
import { getPlanSummary } from '../api/planSummary'
import useObservability from './useObservability'

const POLL_INTERVAL_MS = 10000

/**
 * Hook for unified plan summary data with WebSocket-driven updates and polling fallback.
 *
 * @param {string} projectId - Active project ID
 * @param {Object} options - { pollInterval, useWebSocket }
 */
function usePlanSummary(projectId, options = {}) {
  const { pollInterval = POLL_INTERVAL_MS, useWebSocket = true } = options

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const lastEventRef = useRef(null)

  // WebSocket connection for real-time updates
  const { connected, latestEvent } = useObservability({ autoConnect: useWebSocket })

  const fetchData = useCallback(async () => {
    if (!projectId) return
    try {
      setLoading(true)
      const result = await getPlanSummary(projectId)
      setData(result)
      setError(null)
    } catch (err) {
      if (err.message?.includes('503') || err.message?.includes('not available')) {
        setData(null)
        setError(null)
      } else {
        setError(err.message)
      }
    } finally {
      setLoading(false)
    }
  }, [projectId])

  // Initial fetch
  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Handle WebSocket events for real-time updates
  useEffect(() => {
    if (latestEvent && latestEvent !== lastEventRef.current) {
      lastEventRef.current = latestEvent
      const eventType = latestEvent.type

      if (eventType === 'work_status_change' ||
          eventType === 'issue_created' ||
          eventType === 'issue_updated' ||
          eventType === 'process_map_reevaluation') {
        fetchData()
      }
    }
  }, [latestEvent, fetchData])

  // Fallback polling when WebSocket is disconnected
  useEffect(() => {
    if ((!useWebSocket || !connected) && pollInterval > 0) {
      const interval = setInterval(fetchData, pollInterval)
      return () => clearInterval(interval)
    }
  }, [fetchData, pollInterval, connected, useWebSocket])

  return {
    data,
    loading,
    error,
    refresh: fetchData,
  }
}

export default usePlanSummary
