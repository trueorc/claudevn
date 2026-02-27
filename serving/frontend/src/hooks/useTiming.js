import { useState, useEffect, useCallback } from 'react'
import { getTimingDashboard } from '../api/timing'

function useTiming(options = {}) {
  const { pollInterval = 10000, limit = 20 } = options

  const [dashboard, setDashboard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const data = await getTimingDashboard(limit)
      setDashboard(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [limit])

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

  return {
    dashboard,
    workItems: dashboard?.work_items || [],
    aggregates: dashboard?.aggregates || [],
    totalWorkItems: dashboard?.total_work_items || 0,
    loading,
    error,
    refresh
  }
}

export { useTiming }
export default useTiming
