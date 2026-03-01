import { request } from './index.js'

/**
 * Get decision traces for a specific work item.
 * Answers "Why is this task here?"
 * @param {string} projectId
 * @param {string} itemId
 * @param {number} [limit=20]
 * @returns {Promise<Object[]>} Array of DecisionTrace objects
 */
export async function getTracesForItem(projectId, itemId, limit = 20) {
  return request(
    `/decision-traces/projects/${encodeURIComponent(projectId)}/items/${encodeURIComponent(itemId)}?limit=${limit}`
  )
}

/**
 * Get a trace chain starting from a given trace.
 * Follows related_trace_ids to build a decision chain.
 * @param {string} projectId
 * @param {string} traceId
 * @param {number} [maxDepth=10]
 * @returns {Promise<Object[]>} Array of DecisionTrace objects in chain
 */
export async function getTraceChain(projectId, traceId, maxDepth = 10) {
  return request(
    `/decision-traces/projects/${encodeURIComponent(projectId)}/traces/${encodeURIComponent(traceId)}/chain?max_depth=${maxDepth}`
  )
}
