import { request } from './index.js'

/**
 * Start async auto-processing of a goal.
 * Returns immediately with 202 Accepted.
 * @param {string} goalId - Goal ID to auto-process
 * @param {Object} constraints - Optional constraints (max_issues, focus_areas)
 * @returns {Promise<Object>} AutoProcessAcceptedResponse
 */
export async function autoProcessGoal(goalId, constraints = null) {
  return request(`/goals/${goalId}/auto-process`, {
    method: 'POST',
    body: JSON.stringify(constraints ? { constraints } : {})
  })
}

/**
 * Poll for auto-process progress.
 * @param {string} goalId - Goal ID to check status for
 * @returns {Promise<Object>} ProcessingStatusResponse
 */
export async function getProcessingStatus(goalId) {
  return request(`/goals/${goalId}/processing-status`)
}
