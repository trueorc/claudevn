import { useState, useEffect, useCallback, useRef } from 'react'
import { getProjects, getProject } from '../api/projects'

function useProjects({ pollInterval = 30000, filters = {} } = {}) {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Serialize filters for stable effect dependency
  const filterKey = JSON.stringify({
    status: filters.status || '',
    search: filters.search || '',
    sort: filters.sort || ''
  })

  // Keep current filters in a ref for polling
  const filtersRef = useRef(filters)
  filtersRef.current = filters

  const load = useCallback(async (currentFilters, signal) => {
    try {
      const data = await getProjects(currentFilters)
      if (!signal?.aborted) {
        setProjects(data)
        setError(null)
      }
    } catch (err) {
      if (!signal?.aborted) {
        setError(err.message)
        setProjects([])
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false)
      }
    }
  }, [])

  const refresh = useCallback(() => {
    load(filtersRef.current)
  }, [load])

  useEffect(() => {
    const abortController = new AbortController()
    setLoading(true)
    load(filtersRef.current, abortController.signal)

    let interval
    if (pollInterval > 0) {
      interval = setInterval(() => load(filtersRef.current), pollInterval)
    }

    return () => {
      abortController.abort()
      if (interval) clearInterval(interval)
    }
  }, [load, pollInterval, filterKey])

  return { projects, loading, error, refresh }
}

export function useProject(projectId) {
  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    if (!projectId) {
      setLoading(false)
      return
    }

    try {
      const data = await getProject(projectId)
      setProject(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  return { project, loading, error, refresh: load }
}

export default useProjects
