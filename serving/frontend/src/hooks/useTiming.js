import { useState, useEffect, useCallback } from 'react'
import { getTimingDashboard } from '../api/timing'

function useTiming(projectId, options = {}) {
  const { pollInterval = 10000, limit = 20 } = options

  const [dashboard, setDashboard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

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

  useEffect(() => {
    load()

    if (pollInterval > 0 && projectId) {
      const interval = setInterval(load, pollInterval)
      return () => clearInterval(interval)
    }
  }, [load, pollInterval, projectId])

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
