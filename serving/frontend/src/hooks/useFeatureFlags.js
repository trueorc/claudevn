/**
 * Hook for feature flag management and consumption.
 *
 * Usage:
 *   const { isEnabled, flags, toggle } = useFeatureFlags()
 *   if (isEnabled('new-dashboard')) { ... }
 */

import { useState, useEffect, useCallback } from 'react'
import { listFeatureFlags, toggleFeatureFlag, createFeatureFlag, deleteFeatureFlag } from '../api/featureFlags'

const POLL_INTERVAL = 30000 // 30s

export function useFeatureFlags() {
  const [flags, setFlags] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const data = await listFeatureFlags()
      setFlags(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, POLL_INTERVAL)
    return () => clearInterval(id)
  }, [load])

  const isEnabled = useCallback(
    (name) => {
      const flag = flags.find((f) => f.name === name)
      return flag ? flag.enabled : false
    },
    [flags]
  )

  const toggle = useCallback(
    async (name, enabled) => {
      try {
        const updated = await toggleFeatureFlag(name, enabled)
        setFlags((prev) => prev.map((f) => (f.name === name ? updated : f)))
        return updated
      } catch (err) {
        setError(err.message)
        throw err
      }
    },
    []
  )

  const create = useCallback(
    async (flag) => {
      try {
        const created = await createFeatureFlag(flag)
        setFlags((prev) => [...prev, created])
        return created
      } catch (err) {
        setError(err.message)
        throw err
      }
    },
    []
  )

  const remove = useCallback(
    async (name) => {
      try {
        await deleteFeatureFlag(name)
        setFlags((prev) => prev.filter((f) => f.name !== name))
      } catch (err) {
        setError(err.message)
        throw err
      }
    },
    []
  )

  return { flags, loading, error, isEnabled, toggle, create, remove, refresh: load }
}
