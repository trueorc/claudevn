/**
 * Auth hook for Claude token-based credential management.
 *
 * Polls auth status and provides token submission.
 * Treats 404 from status endpoint as "auth disabled" (authenticated).
 *
 * After authentication, continues polling at a lower frequency (60s)
 * to detect token expiration. When expired, sets `expired: true`
 * and provides a `reauth` action.
 *
 * Supports "skip setup" mode where users can bypass token setup and
 * access the app. Skip preference is stored in localStorage.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { getAuthStatus, submitToken as apiSubmitToken } from '../api/auth.js'

const POLL_FAST_MS = 3000
const POLL_SLOW_MS = 60000
const SKIP_SETUP_KEY = 'claudevn_setup_skipped'

export function useAuth() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [authenticated, setAuthenticated] = useState(false)
  const [expired, setExpired] = useState(false)
  const [expiringAt, setExpiringAt] = useState(null)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [skipped, setSkipped] = useState(() => {
    return localStorage.getItem(SKIP_SETUP_KEY) === 'true'
  })
  const intervalRef = useRef(null)
  const wasAuthenticatedRef = useRef(false)

  const setPollInterval = useCallback((intervalMs) => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    if (intervalMs > 0) {
      intervalRef.current = setInterval(() => {
        checkStatusRef.current()
      }, intervalMs)
    }
  }, [])

  const checkStatusRef = useRef(null)

  const checkStatus = useCallback(async () => {
    try {
      const data = await getAuthStatus()
      setStatus(data.status)
      setError(null)
      setMessage(data.message || null)
      setExpiringAt(data.expiring_at || null)
      setLoading(false)

      if (data.authenticated) {
        setAuthenticated(true)
        setExpired(false)
        // Clear skip flag if user actually authenticated
        if (skipped) {
          localStorage.removeItem(SKIP_SETUP_KEY)
          setSkipped(false)
        }
        if (!wasAuthenticatedRef.current) {
          wasAuthenticatedRef.current = true
          setPollInterval(POLL_SLOW_MS)
        }
      } else if (wasAuthenticatedRef.current) {
        // Was authenticated, now not — token expired
        setExpired(true)
        setAuthenticated(true) // keep showing main app with banner
        setPollInterval(POLL_FAST_MS)
      } else if (skipped) {
        // User skipped setup, treat as authenticated
        setAuthenticated(true)
        setExpired(false)
      } else {
        setAuthenticated(false)
        setExpired(false)
      }
    } catch (err) {
      // If skipped, allow app access even on error
      if (skipped) {
        setAuthenticated(true)
      } else {
        setAuthenticated(false)
      }
      setError(err.message || 'Cannot connect to server')
      setLoading(false)
    }
  }, [setPollInterval, skipped])

  checkStatusRef.current = checkStatus

  useEffect(() => {
    checkStatus()
    intervalRef.current = setInterval(checkStatus, POLL_FAST_MS)
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [checkStatus])

  const submitToken = useCallback(async (token) => {
    try {
      setMessage(null)
      const data = await apiSubmitToken(token)
      setMessage(data.message || null)
      // Poll quickly to pick up authenticated status
      setPollInterval(POLL_FAST_MS)
    } catch (err) {
      setMessage(err.message || 'Failed to submit token')
    }
  }, [setPollInterval])

  const reauth = useCallback(() => {
    setExpired(false)
    wasAuthenticatedRef.current = false
    setAuthenticated(false)
  }, [])

  const skipSetup = useCallback(() => {
    localStorage.setItem(SKIP_SETUP_KEY, 'true')
    setSkipped(true)
    setAuthenticated(true)
  }, [])

  const unskipSetup = useCallback(() => {
    localStorage.removeItem(SKIP_SETUP_KEY)
    setSkipped(false)
    setAuthenticated(false)
    checkStatusRef.current()
  }, [])

  return {
    status,
    loading,
    authenticated,
    expired,
    expiringAt,
    error,
    message,
    submitToken,
    reauth,
    skipSetup,
    unskipSetup,
  }
}
