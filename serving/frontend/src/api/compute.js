import { request } from './index.js'

export async function getComputeInstances(status = null) {
  const params = status ? `?status=${status}` : ''
  const response = await request(`/compute${params}`)
  return response.instances || []
}

export async function getComputeInstance(instanceId) {
  return request(`/compute/${instanceId}`)
}

export async function deregisterComputeInstance(instanceId) {
  return request(`/compute/${instanceId}`, { method: 'DELETE' })
}

export async function getComputeStats() {
  return request('/compute/stats/summary')
}

export async function getAggregatedCapabilities() {
  return request('/compute/capabilities/aggregated')
}

export async function updateComputeProjects(instanceId, projectIds) {
  return request(`/compute/${instanceId}/projects`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_ids: projectIds })
  })
}

export async function drainComputeInstance(instanceId, autoDeregister = false) {
  return request(`/compute/${instanceId}/drain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ auto_deregister: autoDeregister })
  })
}

export async function getDrainStatus(instanceId) {
  return request(`/compute/${instanceId}/drain`)
}

export async function cancelDrain(instanceId) {
  return request(`/compute/${instanceId}/drain`, { method: 'DELETE' })
}

export async function getComputeLogs(instanceId, lines = 100) {
  return request(`/logs/compute/${instanceId}?lines=${lines}`)
}
