/**
 * Users API client for registration, login, and profile management.
 */

import { API_BASE, request as apiRequest } from './index.js'

export async function registerUser(username, email) {
  const response = await fetch(`${API_BASE}/users/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email: email || undefined })
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || 'Registration failed')
  }
  return response.json()
}

export async function loginUser(username) {
  const response = await fetch(`${API_BASE}/users/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username })
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || 'Login failed')
  }
  return response.json()
}

export async function getUserProfile() {
  try {
    return await apiRequest('/users/me')
  } catch (err) {
    if (err.message?.includes('401') || err.message?.includes('Unauthorized')) {
      return null
    }
    throw err
  }
}

export async function updateUserProfile(data) {
  return apiRequest('/users/me', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}
