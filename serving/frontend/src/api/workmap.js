import { request } from './index.js'

export async function getWorkMapStats(projectId = null) {
  const params = new URLSearchParams()
  if (projectId) params.append('project_id', projectId)
  const queryString = params.toString()
  return request(`/workmap/stats${queryString ? `?${queryString}` : ''}`)
}

export async function getWorkMap(projectId = null) {
  const params = new URLSearchParams()
  if (projectId) params.append('project_id', projectId)
  const queryString = params.toString()
  return request(`/workmap${queryString ? `?${queryString}` : ''}`)
}

export async function getActiveWork(projectId = null) {
  const params = new URLSearchParams()
  if (projectId) params.append('project_id', projectId)
  const queryString = params.toString()
  const response = await request(`/workmap/in-progress${queryString ? `?${queryString}` : ''}`)
  return response.items || []
}

export function deriveIssuesByGoal(workmap) {
  const goals = workmap.goals?.items || []
  const issues = workmap.issues?.items || []

  return goals.map(goal => ({
    ...goal,
    issues: issues.filter(issue => issue.goal_id === goal.goal_id)
  }))
}

export function deriveGraphData(workmap) {
  const issues = workmap.issues?.items || []
  const goals = workmap.goals?.items || []

  const nodes = []
  const edges = []

  goals.forEach(goal => {
    nodes.push({
      id: `goal-${goal.goal_id}`,
      type: 'goal',
      data: goal
    })
  })

  issues.forEach(issue => {
    nodes.push({
      id: `issue-${issue.issue_id}`,
      type: 'issue',
      data: issue
    })

    if (issue.goal_id) {
      edges.push({
        source: `goal-${issue.goal_id}`,
        target: `issue-${issue.issue_id}`
      })
    }

    if (issue.depends_on) {
      issue.depends_on.forEach(depId => {
        edges.push({
          source: `issue-${depId}`,
          target: `issue-${issue.issue_id}`
        })
      })
    }
  })

  return { nodes, edges }
}

export async function getGoals(includeArchived = false, projectId = null) {
  const params = new URLSearchParams()
  if (includeArchived) params.append('include_archived', 'true')
  if (projectId) params.append('project_id', projectId)
  const queryString = params.toString()
  const response = await request(`/goals${queryString ? `?${queryString}` : ''}`)
  return response.items || []
}

export async function createGoal(goalData) {
  return request('/goals', {
    method: 'POST',
    body: JSON.stringify(goalData)
  })
}

export async function updateIssuePriority(issueId, priority) {
  return request(`/issues/${issueId}`, {
    method: 'PATCH',
    body: JSON.stringify({ priority })
  })
}

export async function createIssue(issueData) {
  return request('/issues', {
    method: 'POST',
    body: JSON.stringify(issueData)
  })
}

export async function getIssue(issueId) {
  return request(`/issues/${issueId}`)
}

export async function updateIssue(issueId, updates) {
  return request(`/issues/${issueId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates)
  })
}

export async function updateIssueStatus(issueId, status, reason = null) {
  let url = `/issues/${issueId}/status?status=${encodeURIComponent(status)}`
  if (reason) {
    url += `&reason=${encodeURIComponent(reason)}`
  }
  return request(url, {
    method: 'POST'
  })
}

export async function deleteIssue(issueId) {
  return request(`/issues/${issueId}`, {
    method: 'DELETE'
  })
}

export async function getAllIssues(filters = {}) {
  const params = new URLSearchParams()
  if (filters.status) params.append('status', filters.status)
  if (filters.priority) params.append('priority', filters.priority)
  if (filters.goal_id) params.append('goal_id', filters.goal_id)
  if (filters.release_id) params.append('release_id', filters.release_id)
  if (filters.project_id) params.append('project_id', filters.project_id)
  const queryString = params.toString()
  return request(`/issues${queryString ? `?${queryString}` : ''}`)
}

// Goal Comments API
export async function getGoalComments(goalId) {
  return request(`/goals/${goalId}/comments`)
}

export async function createGoalComment(goalId, commentData) {
  return request(`/goals/${goalId}/comments`, {
    method: 'POST',
    body: JSON.stringify(commentData)
  })
}

export async function updateGoalComment(goalId, commentId, updates) {
  return request(`/goals/${goalId}/comments/${commentId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates)
  })
}

export async function deleteGoalComment(goalId, commentId) {
  return request(`/goals/${goalId}/comments/${commentId}`, {
    method: 'DELETE'
  })
}

// Goal evaluation summary
export async function getGoalEvaluationSummary(goalId) {
  return request(`/goals/${goalId}/evaluation-summary`)
}

// Goal decomposition
export async function getGoalDecomposition(goalId) {
  return request(`/goals/${goalId}/decomposition`)
}

// Goal progress metrics
export async function getGoalProgress(goalId) {
  return request(`/goals/${goalId}/progress`)
}

// Goal deletion
export async function deleteGoal(goalId, hard = false) {
  return request(`/goals/${goalId}${hard ? '?hard=true' : ''}`, {
    method: 'DELETE'
  })
}

export async function restoreGoal(goalId) {
  return request(`/goals/${goalId}/restore`, {
    method: 'POST'
  })
}

export async function archiveGoal(goalId) {
  return request(`/goals/${goalId}/archive`, {
    method: 'POST'
  })
}

export async function unarchiveGoal(goalId) {
  return request(`/goals/${goalId}/unarchive`, {
    method: 'POST'
  })
}

// Release API
export async function getReleases(status = null) {
  const params = new URLSearchParams()
  if (status) params.append('status', status)
  const queryString = params.toString()
  return request(`/releases${queryString ? `?${queryString}` : ''}`)
}

export async function createRelease(releaseData) {
  return request('/releases', {
    method: 'POST',
    body: JSON.stringify(releaseData)
  })
}

export async function getRelease(releaseId) {
  return request(`/releases/${releaseId}`)
}

export async function updateRelease(releaseId, updates) {
  return request(`/releases/${releaseId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates)
  })
}

export async function deleteRelease(releaseId) {
  return request(`/releases/${releaseId}`, {
    method: 'DELETE'
  })
}

export async function getReleaseIssues(releaseId) {
  return request(`/releases/${releaseId}/issues`)
}

// Bucket Tree API
export async function getBucketTree(projectId) {
  return request(`/workmap/bucket-tree?project_id=${encodeURIComponent(projectId)}`)
}

export async function getBucketDetail(bucketId, projectId) {
  return request(`/workmap/bucket-tree/${encodeURIComponent(bucketId)}?project_id=${encodeURIComponent(projectId)}`)
}

export async function retryGoalPlanning(goalId) {
  return request(`/workmap/goals/${goalId}/retry-planning`, { method: 'POST' })
}
