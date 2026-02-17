import { useState, useEffect, useCallback } from 'react'
import { getMarketplaces, getMarketplaceStats } from '../api/marketplace'

function useMarketplace(options = {}) {
  const { pollInterval = 10000, status = null } = options

  const [marketplaces, setMarketplaces] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const [marketplacesData, statsData] = await Promise.all([
        getMarketplaces(status),
        getMarketplaceStats()
      ])
      setMarketplaces(marketplacesData)
      setStats(statsData)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [status])

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

  return { marketplaces, stats, loading, error, refresh }
}

export default useMarketplace
