/**
 * Hook for the unified project plan.
 *
 * Loads all work units across directives, superseded units,
 * and unresolved conflicts from the /project/{id}/plan endpoint.
 * Auto-refreshes on plan reconciliation SSE events.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { getProjectPlan } from '../api/workUnits'

export default function useProjectPlan(projectId) {
  const [activeUnits, setActiveUnits] = useState([])
  const [supersededUnits, setSupersededUnits] = useState([])
  const [conflicts, setConflicts] = useState([])
  const [directivesContributing, setDirectivesContributing] = useState([])
  const [loading, setLoading] = useState(false)
  const mountedRef = useRef(true)

  const load = useCallback(async () => {
    if (!projectId) {
      setActiveUnits([])
      setSupersededUnits([])
      setConflicts([])
      setDirectivesContributing([])
      return
    }

    setLoading(true)
    try {
      const data = await getProjectPlan(projectId)
      if (!mountedRef.current) return
      setActiveUnits(data?.active_units || [])
      setSupersededUnits(data?.superseded_units || [])
      setConflicts(data?.conflicts || [])
      setDirectivesContributing(data?.directives_contributing || [])
    } catch {
      if (!mountedRef.current) return
      setActiveUnits([])
      setSupersededUnits([])
      setConflicts([])
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    mountedRef.current = true
    load()
    return () => { mountedRef.current = false }
  }, [load])

  return {
    activeUnits,
    supersededUnits,
    conflicts,
    directivesContributing,
    loading,
    refresh: load,
  }
}
