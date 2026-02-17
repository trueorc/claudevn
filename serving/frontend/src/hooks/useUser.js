/**
 * Hook for user authentication and profile management.
 */

import { useState, useEffect, useCallback } from 'react'
import { getUserProfile, registerUser, loginUser, updateUserProfile } from '../api/users'

const TOKEN_KEY = 'claudevn_user_token'

export function useUser() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadProfile = useCallback(async () => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) {
      setLoading(false)
      return
    }

    try {
      const profile = await getUserProfile()
      if (profile) {
        setUser(profile)
      } else {
        // Token invalid/expired
        localStorage.removeItem(TOKEN_KEY)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadProfile()
  }, [loadProfile])

  const register = useCallback(async (username, email) => {
    setError(null)
    try {
      const result = await registerUser(username, email)
      localStorage.setItem(TOKEN_KEY, result.token)
      setUser({
        user_id: result.user_id,
        username: result.username,
        role: result.role,
      })
      return result
    } catch (err) {
      setError(err.message)
      throw err
    }
  }, [])

  const login = useCallback(async (username) => {
    setError(null)
    try {
      const result = await loginUser(username)
      localStorage.setItem(TOKEN_KEY, result.token)
      setUser({
        user_id: result.user_id,
        username: result.username,
        role: result.role,
      })
      return result
    } catch (err) {
      setError(err.message)
      throw err
    }
  }, [])

  const updateProfile = useCallback(async (data) => {
    setError(null)
    try {
      const updated = await updateUserProfile(data)
      setUser(updated)
      return updated
    } catch (err) {
      setError(err.message)
      throw err
    }
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setUser(null)
  }, [])

  return {
    user,
    loading,
    error,
    isAuthenticated: !!user,
    isOwner: user?.role === 'owner',
    register,
    login,
    logout,
    updateProfile,
    refreshProfile: loadProfile,
  }
}
