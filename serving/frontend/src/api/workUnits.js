/**
 * Work unit API for v2.0 decomposition and verification.
 */

import { request } from './index.js'

// -- Decomposition --

export async function getDecomposition(goalId) {
  return request(`/decomposition/${goalId}`)
}

export async function getWorkUnits(goalId) {
  return request(`/decomposition/${goalId}/work-units`)
}

export async function updateWorkUnit(unitId, updates) {
  return request(`/work-units/${unitId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  })
}

export async function approveDecomposition(goalId) {
  return request(`/decomposition/${goalId}/approve`, { method: 'POST' })
}

export async function splitWorkUnit(unitId, splitSpec) {
  return request(`/work-units/${unitId}/split`, {
    method: 'POST',
    body: JSON.stringify(splitSpec),
  })
}

export async function mergeWorkUnits(unitIds) {
  return request(`/work-units/merge`, {
    method: 'POST',
    body: JSON.stringify({ unit_ids: unitIds }),
  })
}

// -- Verification --

export async function getVerificationResults(goalId) {
  return request(`/verification/${goalId}/results`)
}

export async function getUnitVerification(unitId) {
  return request(`/verification/unit/${unitId}`)
}

export async function getIntegrationReport(goalId) {
  return request(`/verification/${goalId}/integration`)
}

export async function retryVerification(unitId) {
  return request(`/verification/unit/${unitId}/retry`, { method: 'POST' })
}

export async function approveUnit(unitId) {
  return request(`/verification/unit/${unitId}/approve`, { method: 'POST' })
}

// -- Coherence --

export async function getCoherenceInsights(projectId) {
  return request(`/decomposition/coherence/${projectId}`)
}

// -- Dispatch queue --

export async function getDispatchQueue() {
  return request('/dispatch/queue')
}

export async function getActiveExecutions() {
  return request('/dispatch/active')
}
