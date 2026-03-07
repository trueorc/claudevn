/**
 * AWS Cognito auth provider.
 * Authenticates via Amplify SDK with JWT tokens.
 */

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

export function createCognitoProvider(setUser, setError, setChallengeName) {
  let configured = false

  return {
    async init(config) {
      if (!configured) {
        Amplify.configure({
          Auth: {
            Cognito: {
              userPoolId: config.user_pool_id,
              userPoolClientId: config.app_client_id,
            }
          }
        })
        configured = true
      }

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
        // No existing session
      }
    },

    async login(email, password) {
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
    },

    async logout() {
      try {
        await signOut()
      } catch {
        // Ignore sign-out errors
      }
    },

    async getAccessToken() {
      try {
        const session = await fetchAuthSession({ forceRefresh: false })
        return session.tokens?.accessToken?.toString() || null
      } catch {
        return null
      }
    },

    async completeNewPassword(newPassword) {
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
    },

    async forgotPassword(email) {
      try {
        await resetPassword({ username: email })
        return { success: true }
      } catch (err) {
        const msg = err.message || 'Failed to send reset code'
        setError(msg)
        return { error: msg }
      }
    },

    async confirmForgotPassword(email, code, newPassword) {
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
    },
  }
}
