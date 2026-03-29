/**
 * Work unit API for v2.0 decomposition and verification.
 */

import { request } from './index.js'

// -- Decomposition --

export async function getWorkUnits(goalId) {
  return request(`/decomposition/${goalId}/work-units`)
}

export async function getPipelineStatus(goalId) {
  return request(`/decomposition/${goalId}/pipeline`)
}

export async function approveDecomposition(goalId) {
  return request(`/decomposition/${goalId}/approve`, { method: 'POST' })
}

// TODO: splitWorkUnit and mergeWorkUnits — implement when recomposition UI is built

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

// -- Compute environment --

export async function getComputeEnvironment(goalId) {
  return request(`/decomposition/${goalId}/environment`)
}

export async function approveComputeEnvironment(goalId) {
  return request(`/decomposition/${goalId}/environment/approve`, { method: 'POST' })
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
