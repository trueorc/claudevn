import { useState, useEffect, useCallback } from 'react'

const API_BASE = '/api/v1'

export default function useNetworkCapacity({ pollInterval = 30000 } = {}) {
  const [capacity, setCapacity] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchCapacity = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/network/capacity`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setCapacity(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  const updateCapacity = useCallback(async (maxInstances) => {
    try {
      const res = await fetch(`${API_BASE}/network/capacity`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_compute_instances: maxInstances }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setCapacity(data)
      return data
    } catch (err) {
      setError(err.message)
      throw err
    }
  }, [])

  useEffect(() => {
    fetchCapacity()
    const id = setInterval(fetchCapacity, pollInterval)
    return () => clearInterval(id)
  }, [fetchCapacity, pollInterval])

  return { capacity, loading, error, refresh: fetchCapacity, updateCapacity }
}
