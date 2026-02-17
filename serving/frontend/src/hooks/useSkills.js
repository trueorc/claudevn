import { useState, useEffect, useCallback } from 'react'
import { getSkills, getSkillStats } from '../api/skills'

function useSkills(options = {}) {
  const { pollInterval = 10000, filter = null } = options

  const [skills, setSkills] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const [skillsData, statsData] = await Promise.all([
        getSkills(filter),
        getSkillStats()
      ])
      setSkills(skillsData)
      setStats(statsData)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filter])

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

  return { skills, stats, loading, error, refresh }
}

export default useSkills
