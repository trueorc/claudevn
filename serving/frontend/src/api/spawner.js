import { request } from './index.js'

export async function getSpawnedInstances(state = null) {
  const params = state ? `?state=${state}` : ''
  const response = await request(`/spawner${params}`)
  return response.instances || []
}

export async function getSpawnedInstance(computeId) {
  return request(`/spawner/${computeId}`)
}

export async function spawnCompute(config) {
  return request('/spawner/spawn', {
    method: 'POST',
    body: JSON.stringify(config)
  })
}

export async function stopCompute(computeId, force = false) {
  return request(`/spawner/${computeId}/stop`, {
    method: 'POST',
    body: JSON.stringify({ force })
  })
}

export async function stopAllCompute() {
  return request('/spawner/stop-all', { method: 'POST' })
}

export async function getSpawnerStats() {
  return request('/spawner/stats')
}

export async function getComputeMetrics(computeId) {
  return request(`/spawner/${computeId}/metrics`)
}
