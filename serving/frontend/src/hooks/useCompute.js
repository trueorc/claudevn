import { useState, useEffect, useCallback, useRef } from 'react'
import { getComputeInstances, getComputeStats } from '../api/compute'
import ObservabilityWebSocket from '../services/observabilityWebSocket'

function useCompute(options = {}) {
  const { pollInterval = 3000, status = null, enableWebSocket = true } = options

  const [instances, setInstances] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const wsRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const [instancesData, statsData] = await Promise.all([
        getComputeInstances(status),
        getComputeStats()
      ])
      setInstances(instancesData)
      setStats(statsData)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [status])

  const refresh = useCallback(() => {
    load()
  }, [load])

  useEffect(() => {
    load()

    if (pollInterval > 0) {
      const interval = setInterval(load, pollInterval)
      return () => clearInterval(interval)
    }
  }, [load, pollInterval])

  // WebSocket integration for instant updates
  useEffect(() => {
    if (!enableWebSocket) return

    // Create WebSocket connection
    wsRef.current = new ObservabilityWebSocket()

    // Handle compute_registered events
    const handleComputeRegistered = (eventData) => {
      console.log('[useCompute] Compute registered:', eventData)
      // Trigger immediate refresh instead of polling
      refresh()
    }

    // Handle compute_deregistered events
    const handleComputeDeregistered = (eventData) => {
      console.log('[useCompute] Compute deregistered:', eventData)
      // Trigger immediate refresh instead of polling
      refresh()
    }

    wsRef.current.on('compute_registered', handleComputeRegistered)
    wsRef.current.on('compute_deregistered', handleComputeDeregistered)

    // Connect to WebSocket
    wsRef.current.connect()

    return () => {
      if (wsRef.current) {
        wsRef.current.off('compute_registered', handleComputeRegistered)
        wsRef.current.off('compute_deregistered', handleComputeDeregistered)
        wsRef.current.disconnect()
      }
    }
  }, [enableWebSocket, refresh])

  return { instances, stats, loading, error, refresh }
}

export { useCompute }
export default useCompute
