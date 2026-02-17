import { request } from './index.js'

export async function getCharacterizationStatuses(projectId) {
  return request(`/characterization/${encodeURIComponent(projectId)}`)
}
