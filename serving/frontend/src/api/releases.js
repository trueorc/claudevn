import { request } from './index.js'

export async function listReleases() {
  return request('/releases')
}

export async function getRelease(version) {
  return request(`/releases/${version}`)
}
