import { request } from './index.js'

export async function getMarketplaces(status = null) {
  const params = status ? `?status=${status}` : ''
  const response = await request(`/marketplaces${params}`)
  return response.marketplaces || []
}

export async function getMarketplace(marketplaceId) {
  return request(`/marketplaces/${marketplaceId}`)
}

export async function deregisterMarketplace(marketplaceId) {
  return request(`/marketplaces/${marketplaceId}`, { method: 'DELETE' })
}

export async function getMarketplaceStats() {
  return request('/marketplaces/stats/summary')
}

export async function getAggregatedMarketplaceStats() {
  return request('/marketplaces/stats/aggregated')
}

export async function getMarketplaceLogs(marketplaceId, lines = 100) {
  return request(`/logs/marketplace/${marketplaceId}?lines=${lines}`)
}
