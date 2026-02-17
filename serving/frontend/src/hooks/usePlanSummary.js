import { useState, useCallback, useEffect, useRef } from 'react'
import { getPlanSummary } from '../api/planSummary'

const POLL_INTERVAL_MS = 10000

/**
 * Hook for unified plan summary data with polling.
 *
 * @param {string} projectId - Active project ID
 * @param {Object} options - { pollInterval }
 */
function usePlanSummary(projectId, options = {}) {
  const { pollInterval = POLL_INTERVAL_MS } = options

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const pollRef = useRef(null)

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

  useEffect(() => {
    fetchData()

    if (pollInterval > 0) {
      pollRef.current = setInterval(fetchData, pollInterval)
      return () => clearInterval(pollRef.current)
    }
  }, [fetchData, pollInterval])

  return {
    data,
    loading,
    error,
    refresh: fetchData,
  }
}

export default usePlanSummary
