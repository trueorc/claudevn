import { useState, useEffect, useCallback } from 'react'
import { getAuthStatus, listTokens } from '../api/auth'

/**
 * Hook for fetching auth token data for all components.
 *
 * Returns a map of componentId -> auth info for easy lookup,
 * plus system-level auth stats.
 */
function useAuthTokens(options = {}) {
  const { pollInterval = 10000 } = options

  const [tokenMap, setTokenMap] = useState({})
  const [systemStatus, setSystemStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const [statusData, tokensData] = await Promise.all([
        getAuthStatus(),
        listTokens().catch(() => ({ items: [] }))
      ])
      setSystemStatus(statusData)

      // Build lookup map: componentId -> token info
      const map = {}
      for (const item of tokensData.items || []) {
        map[item.component_id] = item
      }
      setTokenMap(map)
      setError(null)
    } catch (err) {
      // If auth is disabled, don't treat as error
      if (err.message?.includes('404')) {
        setSystemStatus({ status: 'disabled', authenticated: true })
        setError(null)
      } else {
        setError(err.message)
      }
    } finally {
      setLoading(false)
    }
  }, [])

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

  /**
   * Get auth status for a specific component.
   * Returns: { status, authorized_at, expires_at, component_type, isExpiringSoon }
   */
  const getComponentAuth = useCallback((componentId) => {
    const info = tokenMap[componentId]
    if (!info) {
      return { status: 'unauthorized', isExpiringSoon: false }
    }

    let isExpiringSoon = false
    if (info.status === 'active' && info.expires_at) {
      const expiresAt = new Date(info.expires_at)
      const daysUntil = (expiresAt - Date.now()) / (1000 * 60 * 60 * 24)
      isExpiringSoon = daysUntil <= 30 && daysUntil > 0
    }

    return {
      ...info,
      isExpiringSoon
    }
  }, [tokenMap])

  return { tokenMap, systemStatus, loading, error, refresh, getComponentAuth }
}

export default useAuthTokens
