/**
 * Bypass auth provider — no login required.
 * Auto-authenticates with a dev user identity.
 */

const BYPASS_USER = {
  email: 'dev@localhost',
  sub: 'bypass-dev-user',
  username: 'dev',
  groups: ['admin'],
}

export function createBypassProvider() {
  return {
    user: BYPASS_USER,

    async login() {
      return { success: true }
    },

    async logout() {
      // No-op in bypass mode
    },

    async getAccessToken() {
      return null
    },

    // Cognito-specific — not applicable
    completeNewPassword: null,
    forgotPassword: null,
    confirmForgotPassword: null,
    challengeName: null,
  }
}
