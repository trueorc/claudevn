import { useState, useEffect, useCallback, useMemo } from 'react'
import { getCharacterizationStatuses } from '../api/characterization'

/**
 * Fetches characterization data for a project and returns a lookup map.
 * Map shape: { [item_id]: { status, ontology_tags } }
 */
function useCharacterizationStatuses(projectId, options = {}) {
  const { pollInterval = 10000 } = options
  const [statusMap, setStatusMap] = useState({})
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!projectId) return
    try {
      setLoading(true)
      const response = await getCharacterizationStatuses(projectId)
      const map = {}
      for (const result of (response.results || [])) {
        map[result.item_id] = {
          status: result.status,
          ontology_tags: result.ontology_tags || null,
        }
      }
      setStatusMap(map)
    } catch {
      // Characterization data is supplementary — fail silently
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  // Poll for updates (characterization is async)
  useEffect(() => {
    if (!projectId || pollInterval <= 0) return
    const interval = setInterval(load, pollInterval)
    return () => clearInterval(interval)
  }, [load, pollInterval, projectId])

  const hasPending = useMemo(() => {
    return Object.values(statusMap).some(
      v => v.status === 'pending' || v.status === 'in_progress'
    )
  }, [statusMap])

  return { statusMap, loading, hasPending, refresh: load }
}

export default useCharacterizationStatuses
