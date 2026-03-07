/**
 * Unified auth context with pluggable providers.
 *
 * Fetches auth mode from the backend, then delegates to the
 * appropriate provider (bypass, local, or cognito).
 *
 * All consumers use useAuth() — they never need to know which
 * provider is active.
 */

import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { setTokenGetter } from '../../api/index'
import { createBypassProvider } from './BypassAuthProvider'
import { createLocalProvider } from './LocalAuthProvider'
import { createCognitoProvider } from './CognitoAuthProvider'

const AuthContext = createContext(null)

async function fetchAuthConfig() {
  const resp = await fetch('/api/v1/auth/cognito-config')
  if (!resp.ok) throw new Error('Failed to fetch auth config')
  return resp.json()
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [authMode, setAuthMode] = useState(null)
  const [error, setError] = useState(null)
  const [challengeName, setChallengeName] = useState(null)
  const providerRef = useRef(null)

  useEffect(() => {
    let cancelled = false

    async function init() {
      try {
        const config = await fetchAuthConfig()
        if (cancelled) return

        const mode = config.auth_mode
        setAuthMode(mode)

        let provider
        switch (mode) {
          case 'bypass':
            provider = createBypassProvider()
            setUser(provider.user)
            break

          case 'local':
            provider = createLocalProvider(setUser, setError)
            await provider.init()
            break

          case 'cognito':
            provider = createCognitoProvider(setUser, setError, setChallengeName)
            await provider.init(config)
            break

          default:
            throw new Error(`Unknown auth mode: ${mode}`)
        }

        providerRef.current = provider
        setTokenGetter(() => provider.getAccessToken())
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    init()
    return () => { cancelled = true }
  }, [])

  const login = useCallback(async (username, password) => {
    setError(null)
    if (!providerRef.current) return { error: 'Auth not initialized' }
    return providerRef.current.login(username, password)
  }, [])

  const logout = useCallback(async () => {
    if (!providerRef.current) return
    await providerRef.current.logout()
    setUser(null)
    setChallengeName(null)
  }, [])

  const getAccessToken = useCallback(async () => {
    if (!providerRef.current) return null
    return providerRef.current.getAccessToken()
  }, [])

  const completeNewPassword = useCallback(async (newPassword) => {
    setError(null)
    if (!providerRef.current?.completeNewPassword) return { error: 'Not supported' }
    return providerRef.current.completeNewPassword(newPassword)
  }, [])

  const forgotPassword = useCallback(async (email) => {
    setError(null)
    if (!providerRef.current?.forgotPassword) return { error: 'Not supported' }
    return providerRef.current.forgotPassword(email)
  }, [])

  const confirmForgotPassword = useCallback(async (email, code, newPassword) => {
    setError(null)
    if (!providerRef.current?.confirmForgotPassword) return { error: 'Not supported' }
    return providerRef.current.confirmForgotPassword(email, code, newPassword)
  }, [])

  const value = {
    user,
    loading,
    authMode,
    error,
    challengeName,
    isAuthenticated: !!user,
    isBypass: authMode === 'bypass',
    isLocal: authMode === 'local',
    login,
    logout,
    completeNewPassword,
    forgotPassword,
    confirmForgotPassword,
    getAccessToken,
    clearError: () => setError(null),
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
