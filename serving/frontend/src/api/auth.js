/**
 * Auth API client for Claude token-based credential management.
 */

import { API_BASE } from './index.js'

export async function getAuthStatus() {
  const response = await fetch(`${API_BASE}/auth/status`)
  if (response.status === 404) {
    return { status: 'disabled', authenticated: true }
  }
  if (!response.ok) {
    throw new Error(`Auth status request failed: ${response.statusText}`)
  }
  return response.json()
}

export async function submitToken(token, componentId = 'serving', componentType = 'serving') {
  const response = await fetch(`${API_BASE}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, component_id: componentId, component_type: componentType })
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `Token submission failed: ${response.statusText}`)
  }
  return response.json()
}

export async function getTokenInfo(componentId) {
  const response = await fetch(`${API_BASE}/auth/token/${componentId}`)
  if (response.status === 404) {
    return null
  }
  if (!response.ok) {
    throw new Error(`Token info request failed: ${response.statusText}`)
  }
  return response.json()
}

export async function revokeToken(componentId) {
  const response = await fetch(`${API_BASE}/auth/token/${componentId}`, {
    method: 'DELETE'
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `Token revoke failed: ${response.statusText}`)
  }
  return response.json()
}

export async function listTokens() {
  const response = await fetch(`${API_BASE}/auth/tokens`)
  if (!response.ok) {
    throw new Error(`Token list request failed: ${response.statusText}`)
  }
  return response.json()
}

export async function logout() {
  const response = await fetch(`${API_BASE}/auth/logout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `Logout request failed: ${response.statusText}`)
  }
  return response.json()
}
