import { request } from './index.js'

export async function getSSHKeys() {
  return request('/git/ssh-keys')
}

export async function getSSHKey(keyId) {
  return request(`/git/ssh-keys/${keyId}`)
}

export async function generateSSHKey(description = '') {
  return request('/git/ssh-keys', {
    method: 'POST',
    body: JSON.stringify({ description })
  })
}

export async function deleteSSHKey(keyId) {
  return request(`/git/ssh-keys/${keyId}`, { method: 'DELETE' })
}

export async function getRepoStatus(projectId, repoId) {
  return request(`/projects/${projectId}/repos/${repoId}/status`)
}

export async function syncRepo(projectId, repoId) {
  return request(`/projects/${projectId}/repos/${repoId}/pull`, {
    method: 'POST'
  })
}

export async function pushRepo(projectId, repoId, branch) {
  const params = new URLSearchParams({ branch })
  return request(`/projects/${projectId}/repos/${repoId}/push?${params}`, {
    method: 'POST'
  })
}

export async function cloneRepo(projectId, repoId) {
  return request(`/projects/${projectId}/repos/${repoId}/clone`, {
    method: 'POST'
  })
}
