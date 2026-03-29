import { useState, useEffect, useCallback } from 'react'
import { FolderOpen, CheckCircle2, XCircle, GitBranch, Scissors, Merge, RefreshCw } from 'lucide-react'
import { getGoals, deleteGoal, archiveGoal, unarchiveGoal, getGoalProgress } from '../api/workmap'
import { getWorkUnits, getPipelineStatus, approveDecomposition, getCoherenceInsights, getComputeEnvironment, approveComputeEnvironment } from '../api/workUnits'
import { useProjectContext } from '../contexts/ProjectContext'
import { useConversationContext } from '../contexts/ConversationContext'
import useEventStream from '../hooks/useEventStream'
import GoalHistoryPanel from '../components/goals/GoalHistoryPanel'
import DeleteGoalConfirmDialog from '../components/goals/DeleteGoalConfirmDialog'
import DecompositionSummary from '../components/decomposition/DecompositionSummary'
import CoherencePanel from '../components/decomposition/CoherencePanel'
import DependencyGraph from '../components/decomposition/DependencyGraph'
import ComputeEnvironmentPanel from '../components/decomposition/ComputeEnvironmentPanel'
import PipelineStatus from '../components/decomposition/PipelineStatus'
import WorkUnitList from '../components/decomposition/WorkUnitList'
import EmptyState from '../components/common/EmptyState'
import Spinner from '../components/common/Spinner'
import { PageSubtitle } from '../components/common/InlineHint'
import '../components/goals/Goals.css'
import './GoalsPage.css'

function GoalsPage() {
  const { activeProject } = useProjectContext()
  const projectId = activeProject?.project_id || null
  const { setActiveGoal, clearActiveGoal } = useConversationContext()

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

  // Work units for selected goal
  const [workUnits, setWorkUnits] = useState([])
  const [workUnitsLoading, setWorkUnitsLoading] = useState(false)
  const [approving, setApproving] = useState(false)

  // Coherence analysis across all goals
  const [coherenceInsights, setCoherenceInsights] = useState([])
  const [coherenceLoading, setCoherenceLoading] = useState(false)

  // Pipeline status and compute environment for selected goal
  const [pipelineData, setPipelineData] = useState(null)
  const [computeEnv, setComputeEnv] = useState(null)
  const [envApproving, setEnvApproving] = useState(false)

  // Subscribe to decomposition events for real-time updates
  useEventStream({
    patterns: ['decomposition.*'],
    projectId,
    enabled: !!projectId,
    onEvent: useCallback((event) => {
      if (selectedGoal && event.goal_id === selectedGoal.goal_id) {
        loadWorkUnits(selectedGoal.goal_id)
      }
      // Refresh goal list and coherence on any decomposition event
      loadGoals()
      loadCoherence()
    }, [selectedGoal]), // eslint-disable-line react-hooks/exhaustive-deps
  })

  // Load goals
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

  // Clear on project change
  useEffect(() => {
    setSelectedGoal(null)
    setWorkUnits([])
    clearActiveGoal()
  }, [projectId, clearActiveGoal])

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

  useEffect(() => { loadGoals() }, [loadGoals])
  useEffect(() => { loadCoherence() }, [loadCoherence])

  const loadComputeEnv = useCallback(async (goalId) => {
    try {
      const data = await getComputeEnvironment(goalId)
      setComputeEnv(data)
    } catch {
      setComputeEnv(null)
    }
  }, [])

  // Load project-level compute environment on project change
  useEffect(() => {
    if (projectId) {
      // Load the project-level environment spec
      // When a goal is selected, this updates to that goal's spec
      loadComputeEnv(projectId)
    } else {
      setComputeEnv(null)
    }
  }, [projectId, loadComputeEnv])

  const loadPipeline = useCallback(async (goalId) => {
    try {
      const data = await getPipelineStatus(goalId)
      setPipelineData(data)
    } catch {
      setPipelineData(null)
    }
  }, [])

  useEffect(() => {
    if (selectedGoal) {
      loadWorkUnits(selectedGoal.goal_id)
      loadComputeEnv(selectedGoal.goal_id)
      loadPipeline(selectedGoal.goal_id)
    } else {
      setWorkUnits([])
      setPipelineData(null)
      if (projectId) loadComputeEnv(projectId)
    }
  }, [selectedGoal, projectId, loadWorkUnits, loadComputeEnv, loadPipeline])

  // Handlers
  const handleSelectGoal = useCallback((goal) => {
    setSelectedGoal(goal)
    if (goal) {
      setActiveGoal(goal.goal_id, goal.title || goal.description?.slice(0, 60))
    } else {
      clearActiveGoal()
    }
  }, [setActiveGoal, clearActiveGoal])

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
        setSelectedGoal(null)
        setWorkUnits([])
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
      if (selectedGoal?.goal_id === goal.goal_id) {
        setSelectedGoal(null)
        setWorkUnits([])
      }
      await loadGoals()
    } catch (err) {
      console.error('Failed to archive:', err)
    }
  }, [selectedGoal, loadGoals])

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
    } catch (err) {
      console.error('Failed to approve decomposition:', err)
    } finally {
      setApproving(false)
    }
  }, [selectedGoal, loadWorkUnits])

  const handleApproveEnvironment = useCallback(async () => {
    const goalId = selectedGoal?.goal_id || goals.find(g => g.status !== 'failed')?.goal_id
    if (!goalId) return
    setEnvApproving(true)
    try {
      await approveComputeEnvironment(goalId)
      // Reload to show approved status with copyable command
      await loadComputeEnv(goalId)
    } catch (err) {
      console.error('Failed to approve environment:', err)
    } finally {
      setEnvApproving(false)
    }
  }, [selectedGoal, goals, loadComputeEnv])

  const handleRefresh = useCallback(() => {
    if (selectedGoal) {
      loadWorkUnits(selectedGoal.goal_id)
      loadComputeEnv(selectedGoal.goal_id)
      loadPipeline(selectedGoal.goal_id)
    }
  }, [selectedGoal, loadWorkUnits, loadComputeEnv, loadPipeline])

  // No project
  if (!projectId) {
    return (
      <div className="goals-page">
        <div className="goals-page-header">
          <h1>Decomposition</h1>
          <PageSubtitle>Select a project to get started</PageSubtitle>
        </div>
        <EmptyState icon={FolderOpen} title="Select a Project" description="Select a project from the sidebar to review decompositions." />
      </div>
    )
  }

  const hasDraftUnits = workUnits.length > 0 && workUnits.some(u => u.status === 'draft')
  const hasWorkUnits = workUnits.length > 0

  return (
    <div className="goals-page">
      <div className="goals-page-layout">
        {/* Main content — decomposition workspace */}
        <div className="goals-page-main">
          {/* Header */}
          <div className="goals-page-header">
            <div className="goals-page-header-content">
              <h1>Decomposition</h1>
              <PageSubtitle>
                {selectedGoal
                  ? selectedGoal.title || selectedGoal.description?.slice(0, 80)
                  : `Review and approve decompositions for ${activeProject.name}`
                }
              </PageSubtitle>
            </div>
            {selectedGoal && (
              <div className="goals-page-actions">
                <button className="goals-action-btn goals-action--secondary" onClick={handleRefresh} title="Refresh">
                  <RefreshCw size={14} />
                </button>
                {hasDraftUnits && (
                  <button
                    className="goals-action-btn goals-action--approve"
                    onClick={handleApproveDecomposition}
                    disabled={approving}
                  >
                    <CheckCircle2 size={14} />
                    {approving ? 'Approving...' : 'Approve'}
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Project-level sections — always visible */}
          <CoherencePanel insights={coherenceInsights} loading={coherenceLoading} />
          <ComputeEnvironmentPanel
            environment={computeEnv}
            onApprove={handleApproveEnvironment}
            approving={envApproving}
          />

          {/* Pipeline progress — shows when a goal has been processed */}
          {selectedGoal && pipelineData && (
            <PipelineStatus pipeline={pipelineData} />
          )}

          {/* Goal detail or selection prompt */}
          {!selectedGoal ? (
            <EmptyState
              icon={GitBranch}
              title="Select a Directive"
              description="Choose a directive from the right panel to review its decomposition, independence, and verification readiness."
            />
          ) : workUnitsLoading ? (
            <div className="goals-page-loading"><Spinner size="md" /></div>
          ) : !hasWorkUnits ? (
            <EmptyState
              icon={GitBranch}
              title="No Work Units Yet"
              description="This directive hasn't been decomposed into work units yet. Use the chat sidebar to describe what you'd like done — the system will decompose it into formally specified units."
            />
          ) : (
            <div className="goals-page-workspace">
              {/* Quality summary cards */}
              <DecompositionSummary units={workUnits} />

              {/* Dependency graph */}
              <DependencyGraph units={workUnits} />

              {/* Work unit detail cards */}
              <div className="goals-page-section">
                <div className="goals-page-section-header">
                  <h2>Work Units</h2>
                  <span className="goals-page-section-count">{workUnits.length}</span>
                </div>
                <WorkUnitList units={workUnits} />
              </div>
            </div>
          )}
        </div>

        {/* Right sidebar — goal history */}
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
