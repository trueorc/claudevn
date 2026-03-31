import { useState, useEffect, useCallback } from 'react'
import { FolderOpen } from 'lucide-react'
import { getGoals, deleteGoal, archiveGoal, unarchiveGoal, getGoalProgress } from '../api/workmap'
import { getWorkUnits, getPipelineStatus, getQualityScores, getDependencyChains, approveDecomposition, recomposeDecomposition, resolveConflict, getCoherenceInsights, getComputeEnvironment, getProjectEnvironment, approveProjectEnvironment, approveComputeEnvironment } from '../api/workUnits'
import { getActivityLog } from '../api/dispatch'
import { useProjectContext } from '../contexts/ProjectContext'
import { useConversationContext } from '../contexts/ConversationContext'
import useEventStream from '../hooks/useEventStream'
import useProjectPlan from '../hooks/useProjectPlan'
import useProjectDecompositionSummary, { computeAttentionItems } from '../hooks/useProjectDecompositionSummary'
import GoalHistoryPanel from '../components/goals/GoalHistoryPanel'
import DeleteGoalConfirmDialog from '../components/goals/DeleteGoalConfirmDialog'
import ProjectOverview from '../components/decomposition/ProjectOverview'
import DirectiveDetail from '../components/decomposition/DirectiveDetail'
import EmptyState from '../components/common/EmptyState'
import { PageSubtitle } from '../components/common/InlineHint'
import '../components/goals/Goals.css'
import './GoalsPage.css'

function buildUnitScoreMap(qualityScores) {
  if (!qualityScores?.unit_scores) return {}
  const map = {}
  for (const us of qualityScores.unit_scores) {
    map[us.unit_id] = us.score
  }
  return map
}

function GoalsPage() {
  const { activeProject } = useProjectContext()
  const projectId = activeProject?.project_id || null
  const { setActiveGoal, clearActiveGoal } = useConversationContext()

  // View mode: project overview (default) or directive detail
  const [viewMode, setViewMode] = useState('project') // 'project' | 'directive'

  // Goal list
  const [goals, setGoals] = useState([])
  const [goalsLoading, setGoalsLoading] = useState(true)
  const [selectedGoal, setSelectedGoal] = useState(null)
  const [goalCommentCounts, setGoalCommentCounts] = useState({})
  const [goalProgress, setGoalProgress] = useState({})
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [goalToDelete, setGoalToDelete] = useState(null)
  const [deletingGoal, setDeletingGoal] = useState(false)
  const [showArchived, setShowArchived] = useState(() => {
    const stored = localStorage.getItem('goalsShowArchived')
    return stored === 'true'
  })

  // Selected directive detail state
  const [workUnits, setWorkUnits] = useState([])
  const [workUnitsLoading, setWorkUnitsLoading] = useState(false)
  const [approving, setApproving] = useState(false)
  const [recomposing, setRecomposing] = useState(false)
  const [pipelineData, setPipelineData] = useState(null)
  const [qualityScores, setQualityScores] = useState(null)
  const [chainAnalysis, setChainAnalysis] = useState(null)

  // Project-level state
  const [coherenceInsights, setCoherenceInsights] = useState([])
  const [coherenceLoading, setCoherenceLoading] = useState(false)
  const [projectEnv, setProjectEnv] = useState(null)
  const [computeEnv, setComputeEnv] = useState(null)
  const [envApproving, setEnvApproving] = useState(false)

  // Activity timeline — loaded from Redis, updated by SSE
  const [decompEvents, setDecompEvents] = useState([])
  const [conflictResolving, setConflictResolving] = useState(false)

  // Load persisted events on mount
  useEffect(() => {
    if (!projectId) return
    getActivityLog(projectId).then(data => {
      if (data?.events) setDecompEvents(data.events)
    }).catch(() => {})
  }, [projectId])

  // Unified project plan
  const {
    activeUnits, supersededUnits, conflicts: planConflicts,
    directivesContributing, loading: planLoading, refresh: refreshPlan,
  } = useProjectPlan(projectId)

  // Project-level aggregate data (for per-directive scores/chains)
  const {
    allWorkUnits, allScores, allChains, loading: summaryLoading, invalidateGoal,
  } = useProjectDecompositionSummary(projectId, goals)

  // Attention items (include plan conflicts)
  const attentionItems = [
    ...computeAttentionItems(goals, allWorkUnits, allScores, coherenceInsights, projectEnv),
    ...(planConflicts?.length > 0 ? [{
      type: 'plan_conflict',
      title: 'Plan conflicts',
      detail: `${planConflicts.length} conflict${planConflicts.length !== 1 ? 's' : ''} need review`,
    }] : []),
  ]

  // SSE subscription
  useEventStream({
    patterns: ['decomposition.*', 'coherence.*', 'decomposition.plan_reconciled', 'decomposition.unit_superseded'],
    projectId,
    enabled: !!projectId,
    onEvent: useCallback((event) => {
      // Accumulate events for timeline (cap at 200)
      setDecompEvents(prev => [...prev.slice(-199), event])

      // Invalidate project summary cache for changed goal
      if (event.goal_id) {
        invalidateGoal(event.goal_id)
      }

      // Reload directive detail if viewing the changed goal
      if (selectedGoal && event.goal_id === selectedGoal.goal_id) {
        loadWorkUnits(selectedGoal.goal_id)
      }

      loadGoals()
      loadCoherence()
      refreshPlan()
      loadProjectEnv()
    }, [selectedGoal]), // eslint-disable-line react-hooks/exhaustive-deps
  })

  // --- Data loaders ---

  const loadGoals = useCallback(async () => {
    if (!projectId) {
      setGoals([])
      setGoalsLoading(false)
      return
    }
    try {
      const data = await getGoals(showArchived, projectId)
      const arr = data.goals || data || []
      setGoals(arr)

      const progressMap = {}
      const withProgress = arr.filter(g => g.status === 'in_progress' || g.status === 'done')
      await Promise.allSettled(
        withProgress.map(async (g) => {
          try { progressMap[g.goal_id] = await getGoalProgress(g.goal_id) } catch { /* skip */ }
        })
      )
      setGoalProgress(progressMap)
    } catch (err) {
      console.error('Failed to load goals:', err)
    } finally {
      setGoalsLoading(false)
    }
  }, [showArchived, projectId])

  const loadWorkUnits = useCallback(async (goalId) => {
    setWorkUnitsLoading(true)
    try {
      const data = await getWorkUnits(goalId)
      setWorkUnits(data?.work_units || data || [])
    } catch {
      setWorkUnits([])
    } finally {
      setWorkUnitsLoading(false)
    }
  }, [])

  const loadCoherence = useCallback(async () => {
    if (!projectId) return
    setCoherenceLoading(true)
    try {
      const data = await getCoherenceInsights(projectId)
      setCoherenceInsights(data?.insights || [])
    } catch {
      setCoherenceInsights([])
    } finally {
      setCoherenceLoading(false)
    }
  }, [projectId])

  const loadProjectEnv = useCallback(async () => {
    if (!projectId) { setProjectEnv(null); return }
    try {
      const data = await getProjectEnvironment(projectId)
      setProjectEnv(data)
    } catch {
      setProjectEnv(null)
    }
  }, [projectId])

  const loadComputeEnv = useCallback(async (goalId) => {
    try {
      const data = await getComputeEnvironment(goalId)
      setComputeEnv(data)
    } catch {
      setComputeEnv(null)
    }
  }, [])

  const loadPipeline = useCallback(async (goalId) => {
    try {
      const data = await getPipelineStatus(goalId)
      setPipelineData(data)
    } catch {
      setPipelineData(null)
    }
  }, [])

  const loadScores = useCallback(async (goalId) => {
    try {
      const data = await getQualityScores(goalId)
      setQualityScores(data)
    } catch {
      setQualityScores(null)
    }
  }, [])

  const loadChains = useCallback(async (goalId) => {
    try {
      const data = await getDependencyChains(goalId)
      setChainAnalysis(data)
    } catch {
      setChainAnalysis(null)
    }
  }, [])

  // --- Effects ---

  useEffect(() => { loadGoals() }, [loadGoals])
  useEffect(() => { loadCoherence() }, [loadCoherence])

  // Load project-level environment
  useEffect(() => { loadProjectEnv() }, [loadProjectEnv])

  // Clear on project change
  useEffect(() => {
    setSelectedGoal(null)
    setWorkUnits([])
    setViewMode('project')
    clearActiveGoal()
  }, [projectId, clearActiveGoal])

  // Load directive detail when selected
  useEffect(() => {
    if (selectedGoal) {
      loadWorkUnits(selectedGoal.goal_id)
      loadComputeEnv(selectedGoal.goal_id)
      loadPipeline(selectedGoal.goal_id)
      loadScores(selectedGoal.goal_id)
      loadChains(selectedGoal.goal_id)
    } else {
      setWorkUnits([])
      setComputeEnv(null)
      setPipelineData(null)
      setQualityScores(null)
      setChainAnalysis(null)
    }
  }, [selectedGoal, loadWorkUnits, loadComputeEnv, loadPipeline, loadScores, loadChains])

  // --- Handlers ---

  const handleSelectGoal = useCallback((goal) => {
    setSelectedGoal(goal)
    if (goal) {
      setViewMode('directive')
      setActiveGoal(goal.goal_id, goal.title || goal.description?.slice(0, 60))
    } else {
      setViewMode('project')
      clearActiveGoal()
    }
  }, [setActiveGoal, clearActiveGoal])

  const handleBackToProject = useCallback(() => {
    setSelectedGoal(null)
    setViewMode('project')
    clearActiveGoal()
  }, [clearActiveGoal])

  const handleDeleteGoal = useCallback((goal) => {
    setGoalToDelete(goal)
    setShowDeleteDialog(true)
  }, [])

  const handleConfirmDelete = async () => {
    if (!goalToDelete) return
    setDeletingGoal(true)
    try {
      await deleteGoal(goalToDelete.goal_id)
      if (selectedGoal?.goal_id === goalToDelete.goal_id) {
        handleBackToProject()
      }
      await loadGoals()
      setShowDeleteDialog(false)
      setGoalToDelete(null)
    } catch (err) {
      console.error('Failed to delete:', err)
    } finally {
      setDeletingGoal(false)
    }
  }

  const handleArchiveGoal = useCallback(async (goal) => {
    try {
      await archiveGoal(goal.goal_id)
      if (selectedGoal?.goal_id === goal.goal_id) handleBackToProject()
      await loadGoals()
    } catch (err) {
      console.error('Failed to archive:', err)
    }
  }, [selectedGoal, loadGoals, handleBackToProject])

  const handleUnarchiveGoal = useCallback(async (goal) => {
    try {
      await unarchiveGoal(goal.goal_id)
      await loadGoals()
    } catch (err) {
      console.error('Failed to unarchive:', err)
    }
  }, [loadGoals])

  const handleToggleArchived = useCallback(() => {
    setShowArchived(prev => {
      const next = !prev
      localStorage.setItem('goalsShowArchived', next.toString())
      return next
    })
  }, [])

  const handleApproveDecomposition = useCallback(async () => {
    if (!selectedGoal) return
    setApproving(true)
    try {
      await approveDecomposition(selectedGoal.goal_id)
      await loadWorkUnits(selectedGoal.goal_id)
      invalidateGoal(selectedGoal.goal_id)
    } catch (err) {
      console.error('Failed to approve decomposition:', err)
    } finally {
      setApproving(false)
    }
  }, [selectedGoal, loadWorkUnits, invalidateGoal])

  const handleRecompose = useCallback(async () => {
    if (!selectedGoal) return
    const refinement = window.prompt('What would you like to change about the decomposition?')
    if (!refinement) return
    setRecomposing(true)
    try {
      await recomposeDecomposition(selectedGoal.goal_id, refinement)
      await Promise.all([
        loadWorkUnits(selectedGoal.goal_id),
        loadPipeline(selectedGoal.goal_id),
        loadScores(selectedGoal.goal_id),
        loadChains(selectedGoal.goal_id),
      ])
      invalidateGoal(selectedGoal.goal_id)
    } catch (err) {
      console.error('Failed to recompose:', err)
    } finally {
      setRecomposing(false)
    }
  }, [selectedGoal, loadWorkUnits, loadPipeline, loadScores, loadChains, invalidateGoal])

  const handleResolveConflict = useCallback(async (conflictId, resolution, supersede_unit_id = null) => {
    if (!projectId) return
    setConflictResolving(true)
    try {
      await resolveConflict(projectId, conflictId, resolution, supersede_unit_id)
      await refreshPlan()
    } catch (err) {
      console.error('Failed to resolve conflict:', err)
    } finally {
      setConflictResolving(false)
    }
  }, [projectId, refreshPlan])

  const handleApproveEnvironment = useCallback(async () => {
    if (!projectId) return
    setEnvApproving(true)
    try {
      await approveProjectEnvironment(projectId)
      await loadProjectEnv()
    } catch (err) {
      console.error('Failed to approve environment:', err)
    } finally {
      setEnvApproving(false)
    }
  }, [projectId, loadProjectEnv])

  const handleRefresh = useCallback(() => {
    loadProjectEnv()
    refreshPlan()
    if (selectedGoal) {
      loadWorkUnits(selectedGoal.goal_id)
      loadComputeEnv(selectedGoal.goal_id)
      loadPipeline(selectedGoal.goal_id)
      loadScores(selectedGoal.goal_id)
      loadChains(selectedGoal.goal_id)
    }
  }, [selectedGoal, loadProjectEnv, refreshPlan, loadWorkUnits, loadComputeEnv, loadPipeline, loadScores, loadChains])

  // --- Render ---

  if (!projectId) {
    return (
      <div className="goals-page">
        <div className="goals-page-header">
          <h1>Plan</h1>
          <PageSubtitle>Select a project to get started</PageSubtitle>
        </div>
        <EmptyState icon={FolderOpen} title="Select a Project" description="Select a project from the sidebar to review decompositions." />
      </div>
    )
  }

  // Build confidence map for sidebar indicators
  const confidenceMap = {}
  for (const [gid, scores] of allScores.entries()) {
    if (scores?.score != null) {
      confidenceMap[gid] = { score: scores.score, level: scores.level }
    }
  }

  // Build attention set for sidebar dots
  const attentionGoalIds = new Set(
    attentionItems.filter(i => i.goalId).map(i => i.goalId)
  )

  // Build work unit count map for sidebar
  const workUnitCountMap = {}
  for (const [gid, units] of allWorkUnits.entries()) {
    workUnitCountMap[gid] = units.length
  }

  return (
    <div className="goals-page">
      <div className="goals-page-layout">
        {/* Main content */}
        <div className="goals-page-main">
          {/* Header */}
          <div className="goals-page-header">
            <div className="goals-page-header-content">
              <h1>Plan</h1>
              <PageSubtitle>
                {viewMode === 'directive' && selectedGoal
                  ? selectedGoal.title || selectedGoal.description?.slice(0, 80)
                  : `${activeProject.name} — ${goals.length} directive${goals.length !== 1 ? 's' : ''}`
                }
              </PageSubtitle>
            </div>
          </div>

          {/* View: Project Overview or Directive Detail */}
          {viewMode === 'project' ? (
            <ProjectOverview
              goals={goals}
              activeUnits={activeUnits}
              supersededUnits={supersededUnits}
              conflicts={planConflicts}
              allWorkUnits={allWorkUnits}
              allScores={allScores}
              allChains={allChains}
              attentionItems={attentionItems}
              coherenceInsights={coherenceInsights}
              coherenceLoading={coherenceLoading}
              computeEnv={projectEnv}
              onApproveEnvironment={handleApproveEnvironment}
              envApproving={envApproving}
              onSelectGoal={handleSelectGoal}
              onResolveConflict={handleResolveConflict}
              conflictResolving={conflictResolving}
              decompEvents={decompEvents}
              summaryLoading={summaryLoading}
            />
          ) : (
            <DirectiveDetail
              goal={selectedGoal}
              workUnits={workUnits}
              workUnitsLoading={workUnitsLoading}
              pipelineData={pipelineData}
              qualityScores={qualityScores}
              chainAnalysis={chainAnalysis}
              computeEnv={computeEnv}
              unitScoreMap={buildUnitScoreMap(qualityScores)}
              reconciliation={pipelineData?.reconciliation}
              onBack={handleBackToProject}
              onApprove={handleApproveDecomposition}
              onRefine={handleRecompose}
              onRefresh={handleRefresh}
              onApproveEnvironment={handleApproveEnvironment}
              approving={approving}
              recomposing={recomposing}
              envApproving={envApproving}
            />
          )}
        </div>

        {/* Right sidebar — directive history */}
        <GoalHistoryPanel
          goals={goals}
          selectedGoalId={selectedGoal?.goal_id}
          onSelectGoal={handleSelectGoal}
          onDeleteGoal={handleDeleteGoal}
          onArchiveGoal={handleArchiveGoal}
          onUnarchiveGoal={handleUnarchiveGoal}
          goalCommentCounts={goalCommentCounts}
          goalProgress={goalProgress}
          loading={goalsLoading}
          showArchived={showArchived}
          onToggleShowArchived={handleToggleArchived}
          viewMode={viewMode}
          onBackToProject={handleBackToProject}
          confidenceMap={confidenceMap}
          attentionGoalIds={attentionGoalIds}
          workUnitCountMap={workUnitCountMap}
        />
      </div>

      <DeleteGoalConfirmDialog
        isOpen={showDeleteDialog}
        onClose={() => { setShowDeleteDialog(false); setGoalToDelete(null) }}
        onConfirm={handleConfirmDelete}
        goal={goalToDelete}
        commentCount={goalToDelete ? (goalCommentCounts[goalToDelete.goal_id] || 0) : 0}
        loading={deletingGoal}
      />
    </div>
  )
}

export default GoalsPage
