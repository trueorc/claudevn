import { request } from './index.js'

/**
 * Get unified plan summary for a project.
 * @param {string} projectId
 * @returns {Promise<Object>} PlanSummaryResponse
 */
export async function getPlanSummary(projectId) {
  return request(`/plan/summary?project_id=${encodeURIComponent(projectId)}`)
}
