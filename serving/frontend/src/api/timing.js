import { request } from './index.js'

export async function getTimingDashboard(limit = 20) {
  return request(`/timing/dashboard?limit=${limit}`)
}

export async function getWorkItemTiming(workId, instanceId) {
  return request(`/timing/work/${encodeURIComponent(workId)}/${encodeURIComponent(instanceId)}`)
}

export async function getTimingAggregates(limit = 100) {
  return request(`/timing/aggregates?limit=${limit}`)
}

export async function getRecentTimings(limit = 50) {
  return request(`/timing/recent?limit=${limit}`)
}
