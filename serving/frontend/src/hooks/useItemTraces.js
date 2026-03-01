import { useState, useEffect, useCallback } from 'react'
import { getTracesForItem } from '../api/decisionTraces'

function useItemTraces(projectId, itemId) {
  const [traces, setTraces] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    if (!projectId || !itemId) {
      setTraces([])
      return
    }

    setLoading(true)
    try {
      const data = await getTracesForItem(projectId, itemId)
      setTraces(data || [])
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [projectId, itemId])

  useEffect(() => {
    load()
  }, [load])

  return { traces, loading, error, refresh: load }
}

export default useItemTraces
