import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { Amplify } from 'aws-amplify'
import {
  signIn,
  signOut,
  confirmSignIn,
  resetPassword,
  confirmResetPassword,
  fetchAuthSession,
  getCurrentUser,
} from 'aws-amplify/auth'

const CognitoAuthContext = createContext(null)

// Cognito config is fetched from the backend to avoid hardcoding
async function fetchCognitoConfig() {
  const resp = await fetch('/api/v1/auth/cognito-config')
  if (!resp.ok) throw new Error('Failed to fetch Cognito config')
  return resp.json()
}

export function CognitoAuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [authMode, setAuthMode] = useState(null) // 'cognito' | 'bypass'
  const [error, setError] = useState(null)
  const [challengeName, setChallengeName] = useState(null)
  const configured = useRef(false)

  // Initialize: fetch config and check session
  useEffect(() => {
    let cancelled = false

    async function init() {
      try {
        const config = await fetchCognitoConfig()

        if (cancelled) return

        if (config.auth_mode === 'bypass') {
          setAuthMode('bypass')
          setUser({ email: 'dev@localhost', sub: 'bypass-dev-user', groups: ['admin'] })
          setLoading(false)
          return
        }

        setAuthMode('cognito')

        if (!configured.current) {
          Amplify.configure({
            Auth: {
              Cognito: {
                userPoolId: config.user_pool_id,
                userPoolClientId: config.app_client_id,
              }
            }
          })
          configured.current = true
        }

        // Check for existing session
        try {
          const currentUser = await getCurrentUser()
          const session = await fetchAuthSession()
          const token = session.tokens?.accessToken?.toString()
          if (token) {
            setUser({
              email: currentUser.signInDetails?.loginId || currentUser.username,
              sub: currentUser.userId,
              token,
            })
          }
        } catch {
          // No existing session - that's fine
        }
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    init()
    return () => { cancelled = true }
  }, [])

  const login = useCallback(async (email, password) => {
    setError(null)
    try {
      const result = await signIn({ username: email, password })

      if (result.nextStep?.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
        setChallengeName('NEW_PASSWORD_REQUIRED')
        return { challenge: 'NEW_PASSWORD_REQUIRED' }
      }

      if (result.isSignedIn) {
        const session = await fetchAuthSession()
        const token = session.tokens?.accessToken?.toString()
        const currentUser = await getCurrentUser()
        setUser({
          email: currentUser.signInDetails?.loginId || email,
          sub: currentUser.userId,
          token,
        })
        setChallengeName(null)
        return { success: true }
      }

      return { error: 'Unexpected sign-in state' }
    } catch (err) {
      const msg = err.message || 'Login failed'
      setError(msg)
      return { error: msg }
    }
  }, [])

  const completeNewPassword = useCallback(async (newPassword) => {
    setError(null)
    try {
      const result = await confirmSignIn({ challengeResponse: newPassword })

      if (result.isSignedIn) {
        const session = await fetchAuthSession()
        const token = session.tokens?.accessToken?.toString()
        const currentUser = await getCurrentUser()
        setUser({
          email: currentUser.signInDetails?.loginId || currentUser.username,
          sub: currentUser.userId,
          token,
        })
        setChallengeName(null)
        return { success: true }
      }

      return { error: 'Password change failed' }
    } catch (err) {
      const msg = err.message || 'Password change failed'
      setError(msg)
      return { error: msg }
    }
  }, [])

  const forgotPassword = useCallback(async (email) => {
    setError(null)
    try {
      await resetPassword({ username: email })
      return { success: true }
    } catch (err) {
      const msg = err.message || 'Failed to send reset code'
      setError(msg)
      return { error: msg }
    }
  }, [])

  const confirmForgotPassword = useCallback(async (email, code, newPassword) => {
    setError(null)
    try {
      await confirmResetPassword({
        username: email,
        confirmationCode: code,
        newPassword,
      })
      return { success: true }
    } catch (err) {
      const msg = err.message || 'Failed to reset password'
      setError(msg)
      return { error: msg }
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await signOut()
    } catch {
      // Ignore sign-out errors
    }
    setUser(null)
    setChallengeName(null)
  }, [])

  const getAccessToken = useCallback(async () => {
    if (authMode === 'bypass') return null
    try {
      const session = await fetchAuthSession({ forceRefresh: false })
      return session.tokens?.accessToken?.toString() || null
    } catch {
      return null
    }
  }, [authMode])

  const value = {
    user,
    loading,
    authMode,
    error,
    challengeName,
    isAuthenticated: !!user,
    isBypass: authMode === 'bypass',
    login,
    logout,
    completeNewPassword,
    forgotPassword,
    confirmForgotPassword,
    getAccessToken,
    clearError: () => setError(null),
  }

  return (
    <CognitoAuthContext.Provider value={value}>
      {children}
    </CognitoAuthContext.Provider>
  )
}

export function useCognitoAuth() {
  const context = useContext(CognitoAuthContext)
  if (!context) {
    throw new Error('useCognitoAuth must be used within CognitoAuthProvider')
  }
  return context
}
