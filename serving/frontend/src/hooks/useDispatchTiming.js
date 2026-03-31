/**
 * Hook for dispatch timing metrics.
 * Polls GET /dispatch/timing every 10 seconds.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { getDispatchTiming } from '../api/dispatch'

export default function useDispatchTiming(projectId) {
  const [timing, setTiming] = useState(null)
  const [loading, setLoading] = useState(false)
  const mountedRef = useRef(true)

  const load = useCallback(async () => {
    if (!projectId) { setTiming(null); return }
    setLoading(true)
    try {
      const data = await getDispatchTiming(projectId)
      if (mountedRef.current) setTiming(data)
    } catch {
      // Timing is non-critical — silent fail
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    mountedRef.current = true
    load()
    const interval = setInterval(load, 10000) // 10s polling
    return () => {
      mountedRef.current = false
      clearInterval(interval)
    }
  }, [load])

  return { timing, loading }
}
