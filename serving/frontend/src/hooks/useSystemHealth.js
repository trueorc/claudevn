import { useState, useEffect, useCallback, useRef } from 'react'
import { getSystemHealth } from '../api/sessions'
import useObservability from './useObservability'

function useSystemHealth(options = {}) {
  const { pollInterval = 30000, useWebSocket = true } = options

  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const lastEventRef = useRef(null)

  // WebSocket connection for real-time updates
  const { connected, latestEvent } = useObservability({ autoConnect: useWebSocket })

  const load = useCallback(async () => {
    try {
      const data = await getSystemHealth()
      setHealth(data)
      setLastUpdated(new Date())
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  const refresh = useCallback(() => {
    setLoading(true)
    load()
  }, [load])

  // Handle WebSocket events for real-time updates
  useEffect(() => {
    if (latestEvent && latestEvent !== lastEventRef.current) {
      lastEventRef.current = latestEvent
      const eventType = latestEvent.type

      // Refresh on relevant health-related events
      if (
        eventType === 'compute_registered' ||
        eventType === 'compute_deregistered' ||
        eventType === 'compute_status_change' ||
        eventType === 'marketplace_registered' ||
        eventType === 'marketplace_status_change' ||
        eventType === 'health_check_completed'
      ) {
        load()
      }
    }
  }, [latestEvent, load])

  // Initial load
  useEffect(() => {
    load()
  }, [load])

  // Fallback polling when WebSocket is disconnected
  useEffect(() => {
    if ((!useWebSocket || !connected) && pollInterval > 0) {
      const interval = setInterval(load, pollInterval)
      return () => clearInterval(interval)
    }
  }, [load, pollInterval, connected, useWebSocket])

  // Compute aggregate status from health data
  const getOverallStatus = useCallback(() => {
    if (!health) return 'unknown'
    if (health.status === 'healthy') {
      // Check for degraded services
      const computeByStatus = health.compute_registry?.by_status || {}
      const marketplaceByStatus = health.marketplace_registry?.by_status || {}

      const hasDegraded =
        (computeByStatus.degraded || 0) > 0 ||
        (marketplaceByStatus.degraded || 0) > 0

      const hasOffline =
        (computeByStatus.offline || 0) > 0 ||
        (marketplaceByStatus.offline || 0) > 0

      if (hasOffline) return 'degraded'
      if (hasDegraded) return 'degraded'
      return 'healthy'
    }
    return health.status || 'unknown'
  }, [health])

  return {
    health,
    loading,
    error,
    lastUpdated,
    refresh,
    connected,
    overallStatus: getOverallStatus()
  }
}

export default useSystemHealth
