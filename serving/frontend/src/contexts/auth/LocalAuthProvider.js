/**
 * Local file-based auth provider.
 * Authenticates via POST /api/v1/users/login with username + password.
 * Sessions are persisted in localStorage.
 */

const STORAGE_TOKEN_KEY = 'claudevn_local_token'
const STORAGE_USER_KEY = 'claudevn_local_user'

export function createLocalProvider(setUser, setError) {
  return {
    async init() {
      const savedToken = localStorage.getItem(STORAGE_TOKEN_KEY)
      const savedUser = localStorage.getItem(STORAGE_USER_KEY)
      if (!savedToken || !savedUser) return

      try {
        const parsed = JSON.parse(savedUser)
        const resp = await fetch('/api/v1/users/me', {
          headers: { Authorization: `Bearer ${savedToken}` },
        })
        if (resp.ok) {
          setUser({ ...parsed, token: savedToken })
        } else {
          _clearStorage()
        }
      } catch {
        _clearStorage()
      }
    },

    async login(username, password) {
      try {
        const resp = await fetch('/api/v1/users/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password }),
        })
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}))
          const msg = data.detail || 'Login failed'
          setError(msg)
          return { error: msg }
        }
        const data = await resp.json()
        const userData = {
          email: data.username,
          sub: data.user_id,
          username: data.username,
          role: data.role,
          token: data.token,
        }
        localStorage.setItem(STORAGE_TOKEN_KEY, data.token)
        localStorage.setItem(STORAGE_USER_KEY, JSON.stringify(userData))
        setUser(userData)
        return { success: true }
      } catch (err) {
        const msg = err.message || 'Login failed'
        setError(msg)
        return { error: msg }
      }
    },

    async logout() {
      _clearStorage()
    },

    async getAccessToken() {
      return localStorage.getItem(STORAGE_TOKEN_KEY)
    },

    // Cognito-specific — not applicable
    completeNewPassword: null,
    forgotPassword: null,
    confirmForgotPassword: null,
    challengeName: null,
  }
}

function _clearStorage() {
  localStorage.removeItem(STORAGE_TOKEN_KEY)
  localStorage.removeItem(STORAGE_USER_KEY)
}
