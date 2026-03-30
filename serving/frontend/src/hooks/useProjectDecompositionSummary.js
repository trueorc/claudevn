/**
 * Aggregates decomposition data across all directives in a project.
 *
 * Loads work units, quality scores, and chains for each goal,
 * caches results, and computes attention items for the project overview.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { getWorkUnits, getQualityScores, getDependencyChains } from '../api/workUnits'

/**
 * Derive the workflow state of a directive from its work units.
 */
export function deriveWorkflowState(workUnits, pipelineData) {
  if (!workUnits || workUnits.length === 0) return 'empty'
  if (pipelineData?.steps?.some(s => s.status === 'running')) return 'processing'
  if (workUnits.every(u => u.status === 'draft')) return 'draft'
  if (workUnits.some(u => u.status === 'draft')) return 'review'
  if (workUnits.every(u => u.status === 'ready' || u.status === 'queued')) return 'approved'
  if (workUnits.some(u => u.status === 'queued' || u.status === 'executing')) return 'executing'
  if (workUnits.every(u => u.status === 'completed' || u.status === 'verified')) return 'completed'
  return 'review'
}

/**
 * Compute attention items from aggregated project data.
 */
export function computeAttentionItems(goals, allWorkUnits, allScores, coherenceInsights, computeEnv) {
  const items = []

  for (const goal of goals) {
    const gid = goal.goal_id
    const units = allWorkUnits.get(gid) || []
    const scores = allScores.get(gid)

    if (units.length > 0 && units.some(u => u.status === 'draft')) {
      items.push({
        type: 'approval',
        goalId: gid,
        title: goal.title || goal.description?.slice(0, 60) || gid,
        detail: `${units.filter(u => u.status === 'draft').length} work units awaiting approval`,
      })
    }

    if (scores && scores.score < 60) {
      items.push({
        type: 'low_confidence',
        goalId: gid,
        title: goal.title || goal.description?.slice(0, 60) || gid,
        detail: `Confidence: ${scores.score}/100 (${scores.level})`,
        score: scores.score,
      })
    }
  }

  const highSeverity = (coherenceInsights || []).filter(i => i.severity === 'high')
  if (highSeverity.length > 0) {
    items.push({
      type: 'coherence',
      title: 'Coherence issues',
      detail: `${highSeverity.length} high-severity insight${highSeverity.length !== 1 ? 's' : ''} across goals`,
      count: highSeverity.length,
    })
  }

  if (computeEnv && computeEnv.status === 'proposed') {
    items.push({
      type: 'env_approval',
      title: 'Environment needs approval',
      detail: `${computeEnv.requirements?.length || 0} requirements detected`,
    })
  }

  return items
}

/**
 * Hook: loads and caches decomposition summary data for all directives.
 */
export default function useProjectDecompositionSummary(projectId, goals) {
  const [allWorkUnits, setAllWorkUnits] = useState(new Map())
  const [allScores, setAllScores] = useState(new Map())
  const [allChains, setAllChains] = useState(new Map())
  const [loading, setLoading] = useState(false)
  const cacheRef = useRef({ workUnits: new Map(), scores: new Map(), chains: new Map() })

  const loadAll = useCallback(async (goalIds, force = false) => {
    if (!goalIds || goalIds.length === 0) return

    setLoading(true)
    const cache = cacheRef.current

    const toFetch = force ? goalIds : goalIds.filter(gid => !cache.workUnits.has(gid))

    if (toFetch.length > 0) {
      const results = await Promise.allSettled(
        toFetch.map(async (gid) => {
          const [wuRes, scRes, chRes] = await Promise.allSettled([
            getWorkUnits(gid),
            getQualityScores(gid),
            getDependencyChains(gid),
          ])

          const units = wuRes.status === 'fulfilled' ? (wuRes.value?.work_units || wuRes.value || []) : []
          const scores = scRes.status === 'fulfilled' ? scRes.value : null
          const chains = chRes.status === 'fulfilled' ? chRes.value : null

          return { gid, units, scores, chains }
        })
      )

      for (const r of results) {
        if (r.status === 'fulfilled') {
          const { gid, units, scores, chains } = r.value
          cache.workUnits.set(gid, units)
          if (scores) cache.scores.set(gid, scores)
          if (chains) cache.chains.set(gid, chains)
        }
      }
    }

    setAllWorkUnits(new Map(cache.workUnits))
    setAllScores(new Map(cache.scores))
    setAllChains(new Map(cache.chains))
    setLoading(false)
  }, [])

  // Load when goals change
  useEffect(() => {
    if (goals && goals.length > 0) {
      const goalIds = goals.map(g => g.goal_id)
      loadAll(goalIds)
    }
  }, [goals, loadAll])

  // Invalidate a specific goal (call on SSE events)
  const invalidateGoal = useCallback((goalId) => {
    cacheRef.current.workUnits.delete(goalId)
    cacheRef.current.scores.delete(goalId)
    cacheRef.current.chains.delete(goalId)
    loadAll([goalId], true)
  }, [loadAll])

  // Clear all on project change
  useEffect(() => {
    cacheRef.current = { workUnits: new Map(), scores: new Map(), chains: new Map() }
    setAllWorkUnits(new Map())
    setAllScores(new Map())
    setAllChains(new Map())
  }, [projectId])

  return {
    allWorkUnits,
    allScores,
    allChains,
    loading,
    invalidateGoal,
  }
}
