/**
 * Users API client for registration, login, and profile management.
 */

import { API_BASE } from './index.js'

function authHeaders() {
  const token = localStorage.getItem('claudevn_user_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

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
  const response = await fetch(`${API_BASE}/users/me`, {
    headers: { ...authHeaders() }
  })
  if (response.status === 401) {
    return null
  }
  if (!response.ok) {
    throw new Error('Failed to fetch profile')
  }
  return response.json()
}

export async function updateUserProfile(data) {
  const response = await fetch(`${API_BASE}/users/me`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(data)
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || 'Update failed')
  }
  return response.json()
}
