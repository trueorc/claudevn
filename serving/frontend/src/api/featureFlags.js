/**
 * API client for feature flags.
 */

import { request } from './index'

export async function listFeatureFlags() {
  const data = await request('/feature-flags')
  return data.flags
}

export async function getFeatureFlag(name) {
  return request(`/feature-flags/${encodeURIComponent(name)}`)
}

export async function createFeatureFlag(flag) {
  return request('/feature-flags', {
    method: 'POST',
    body: JSON.stringify(flag),
  })
}

export async function toggleFeatureFlag(name, enabled) {
  return request(`/feature-flags/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  })
}

export async function deleteFeatureFlag(name) {
  return request(`/feature-flags/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
}
