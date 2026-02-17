import { request } from './index.js'

// Project API - will be implemented in backend
export async function getProjects(filters = {}) {
  const params = new URLSearchParams()

  if (filters.status && filters.status !== 'all') {
    params.append('status', filters.status)
  }
  if (filters.search) {
    params.append('search', filters.search)
  }
  if (filters.sort) {
    params.append('sort', filters.sort)
  }

  const queryString = params.toString()
  const url = queryString ? `/projects?${queryString}` : '/projects'
  const response = await request(url)
  return response.items || []
}

export async function getProject(projectId) {
  return request(`/projects/${projectId}`)
}

export async function createProject(data) {
  return request('/projects', {
    method: 'POST',
    body: JSON.stringify(data)
  })
}

export async function updateProject(projectId, data) {
  return request(`/projects/${projectId}`, {
    method: 'PATCH',
    body: JSON.stringify(data)
  })
}

export async function deleteProject(projectId) {
  return request(`/projects/${projectId}`, { method: 'DELETE' })
}

// Repo associations
export async function addRepoToProject(projectId, repoData) {
  return request(`/projects/${projectId}/repos`, {
    method: 'POST',
    body: JSON.stringify(repoData)
  })
}

export async function createInternalRepo(projectId, repoData) {
  return request(`/projects/${projectId}/repos/internal`, {
    method: 'POST',
    body: JSON.stringify(repoData)
  })
}

export async function removeRepoFromProject(projectId, repoId) {
  return request(`/projects/${projectId}/repos/${repoId}`, { method: 'DELETE' })
}

export async function getProjectRepos(projectId) {
  return request(`/projects/${projectId}/repos`)
}

// Activity API
export async function getProjectActivity(projectId, limit = 10) {
  return request(`/projects/${projectId}/activity?limit=${limit}`)
}

// Git integration (existing endpoints)
export async function getRepoBranches(project) {
  return request(`/git/repos/${project}/branches`)
}

export async function getRepoPRs(project) {
  return request(`/git/prs/${project}`)
}
