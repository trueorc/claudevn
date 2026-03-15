import { request } from './index'

export async function getOrchestratorStatus() {
  return request('/orchestrator/status')
}

export async function pauseOrchestrator() {
  return request('/orchestrator/pause', { method: 'POST' })
}

export async function resumeOrchestrator() {
  return request('/orchestrator/resume', { method: 'POST' })
}
