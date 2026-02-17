import { useState, useEffect, useCallback, useRef } from 'react'
import { getWorkItems, getWorkStats } from '../api/work'
import useObservability from './useObservability'

function useWork(options = {}) {
  const { pollInterval = 5000, filters = {}, useWebSocket = true, key = 0 } = options

  const [items, setItems] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const lastEventRef = useRef(null)
  const loadCountRef = useRef(0)

  // WebSocket connection for real-time updates
  const { connected, latestEvent } = useObservability({ autoConnect: useWebSocket })

  const load = useCallback(async () => {
    try {
      const [itemsData, statsData] = await Promise.all([
        getWorkItems(filters),
        getWorkStats()
      ])
      setItems(itemsData)
      setStats(statsData)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filters])

  // Reload when filters or key changes
  useEffect(() => {
    loadCountRef.current += 1
    load()
  }, [load, key])

  const refresh = useCallback(() => {
    load()
  }, [load])

  // Handle WebSocket events for real-time updates
  useEffect(() => {
    if (latestEvent && latestEvent.type === 'work_status_change' && latestEvent !== lastEventRef.current) {
      lastEventRef.current = latestEvent
      const eventData = latestEvent.data

      // Update item in list
      setItems(prevItems =>
        prevItems.map(item =>
          item.work_id === eventData.work_id
            ? {
                ...item,
                status: eventData.new_status,
                assigned_to: eventData.assigned_to,
                progress_percent: eventData.progress_percent
              }
            : item
        )
      )

      // Refresh stats on status change
      getWorkStats().then(setStats).catch(console.error)
    }
  }, [latestEvent])

  // Fallback polling when WebSocket is disconnected
  useEffect(() => {
    // Only poll if WebSocket is not connected OR useWebSocket is disabled
    if ((!useWebSocket || !connected) && pollInterval > 0) {
      const interval = setInterval(load, pollInterval)
      return () => clearInterval(interval)
    }
  }, [load, pollInterval, connected, useWebSocket])

  return { items, stats, loading, error, refresh, connected }
}

export default useWork
