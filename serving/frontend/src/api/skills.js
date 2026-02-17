import { request } from './index.js'

export async function getSkills(filter = null) {
  let params = ''
  if (filter?.tags) {
    params = `?tags=${filter.tags}`
  } else if (filter?.author) {
    params = `?author=${filter.author}`
  }
  const response = await request(`/skills${params}`)
  return response.skills || []
}

export async function getSkill(skillId) {
  return request(`/skills/${skillId}`)
}

export async function getSkillStats() {
  const response = await request('/skills/stats/summary')
  // Transform response to expected format
  return {
    total: response.total_skills || 0,
    total_skills: response.total_skills || 0,
    total_tools: response.total_tools || 0,
    by_author: response.by_author || {}
  }
}

export async function createSkill(skillData) {
  return request('/skills', {
    method: 'POST',
    body: JSON.stringify(skillData)
  })
}

export async function updateSkill(skillId, updateData) {
  return request(`/skills/${skillId}`, {
    method: 'PATCH',
    body: JSON.stringify(updateData)
  })
}

export async function deleteSkill(skillId) {
  return request(`/skills/${skillId}`, {
    method: 'DELETE'
  })
}

export async function getAggregatedSkills(options = {}) {
  const params = new URLSearchParams()
  if (options.marketplace_id) {
    params.set('marketplace_id', options.marketplace_id)
  }
  if (options.tier) {
    params.set('tier', options.tier)
  }
  if (options.include_sources !== undefined) {
    params.set('include_sources', options.include_sources)
  }
  const queryString = params.toString()
  const url = `/skills/aggregated${queryString ? `?${queryString}` : ''}`
  return request(url)
}

export async function getAllTags() {
  const skills = await getSkills()
  const tagSet = new Set()
  skills.forEach(skill => {
    if (skill.tags) {
      skill.tags.forEach(tag => tagSet.add(tag))
    }
  })
  return Array.from(tagSet).sort()
}
