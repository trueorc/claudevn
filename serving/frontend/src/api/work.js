import { request } from './index.js'

export async function getWorkItems(filters = {}) {
  const params = new URLSearchParams()
  if (filters.status) params.append('status', filters.status)
  if (filters.project_id) params.append('project_id', filters.project_id)
  if (filters.assigned_to) params.append('assigned_to', filters.assigned_to)
  if (filters.priority) params.append('priority', filters.priority)

  const query = params.toString()
  const response = await request(`/work${query ? `?${query}` : ''}`)
  return response.items || []
}

export async function getWorkItem(workId) {
  return request(`/work/${workId}`)
}

export async function createWorkItem(data) {
  return request('/work', {
    method: 'POST',
    body: JSON.stringify(data)
  })
}

export async function updateWorkItem(workId, data) {
  return request(`/work/${workId}`, {
    method: 'PUT',
    body: JSON.stringify(data)
  })
}

export async function deleteWorkItem(workId) {
  return request(`/work/${workId}`, { method: 'DELETE' })
}

export async function assignWork(workId, computeId, skills = []) {
  const params = new URLSearchParams()
  params.append('compute_id', computeId)
  if (skills.length > 0) {
    params.append('skills', skills.join(','))
  }
  return request(`/work/${workId}/assign?${params.toString()}`, {
    method: 'POST'
  })
}

export async function unassignWork(workId) {
  return request(`/work/${workId}/unassign`, { method: 'POST' })
}

export async function updateWorkStatus(workId, status, computeId = null) {
  const params = new URLSearchParams()
  params.append('status', status)
  if (computeId) {
    params.append('compute_id', computeId)
  }
  return request(`/work/${workId}/status?${params.toString()}`, {
    method: 'POST'
  })
}

export async function reportWorkProgress(workId, progressPercent, status, note = null, blockers = []) {
  return request(`/work/${workId}/progress`, {
    method: 'POST',
    body: JSON.stringify({
      work_id: workId,
      progress_percent: progressPercent,
      status,
      note,
      blockers
    })
  })
}

export async function addBlocker(workId, blockerType, description, blockingWorkId = null) {
  const params = new URLSearchParams()
  params.append('blocker_type', blockerType)
  params.append('description', description)
  if (blockingWorkId) {
    params.append('blocking_work_id', blockingWorkId)
  }
  return request(`/work/${workId}/blockers?${params.toString()}`, {
    method: 'POST'
  })
}

export async function resolveBlocker(workId, blockerId, resolutionNote = null) {
  const params = new URLSearchParams()
  if (resolutionNote) params.append('resolution_note', resolutionNote)
  const query = params.toString()
  return request(`/work/${workId}/blockers/${blockerId}/resolve${query ? `?${query}` : ''}`, {
    method: 'POST'
  })
}

export async function getWorkDependencies(workId) {
  return request(`/work/${workId}/dependencies`)
}

export async function getWorkStats() {
  return request('/work/stats')
}
