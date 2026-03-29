import { useState, useEffect, useCallback } from 'react'
import { Plus, FolderOpen, MessageSquare, CheckCircle2, GitBranch } from 'lucide-react'
import { getGoals, getGoalComments, deleteGoal, archiveGoal, unarchiveGoal, getGoalProgress, createGoalComment, getIssue } from '../api/workmap'
import { getWorkUnits, approveDecomposition } from '../api/workUnits'
import { useProjectContext } from '../contexts/ProjectContext'
import { useConversationContext, INTENT_MODES } from '../contexts/ConversationContext'
import useIssues from '../hooks/useIssues'
import useDirectivePrompts from '../hooks/useDirectivePrompts'
import useEventStream from '../hooks/useEventStream'
import ConversationTimeline from '../components/directives/ConversationTimeline'
import ConversationInput from '../components/directives/ConversationInput'
import GoalHistoryPanel from '../components/goals/GoalHistoryPanel'
import DeleteGoalConfirmDialog from '../components/goals/DeleteGoalConfirmDialog'
import GoalCompletionCard from '../components/directives/GoalCompletionCard'
import WorkUnitList from '../components/decomposition/WorkUnitList'
import EmptyState from '../components/common/EmptyState'
import Spinner from '../components/common/Spinner'
import InlineHint, { PageSubtitle } from '../components/common/InlineHint'
import '../components/goals/Goals.css'
import '../components/directives/Conversation.css'

function GoalsPage() {
  const { activeProject } = useProjectContext()
  const projectId = activeProject?.project_id || null

  // Goal list management
  const [goals, setGoals] = useState([])
  const [goalsLoading, setGoalsLoading] = useState(true)
  const [selectedGoal, setSelectedGoal] = useState(null)
  const [goalComments, setGoalComments] = useState([])
  const [commentsLoading, setCommentsLoading] = useState(false)
  const [goalCommentCounts, setGoalCommentCounts] = useState({})
  const [goalProgress, setGoalProgress] = useState({})
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [goalToDelete, setGoalToDelete] = useState(null)
  const [deletingGoal, setDeletingGoal] = useState(false)
  const [addingComment, setAddingComment] = useState(false)
  const [goalIssues, setGoalIssues] = useState([])
  const [goalIssuesLoading, setGoalIssuesLoading] = useState(false)
  const [showArchived, setShowArchived] = useState(() => {
    const stored = localStorage.getItem('goalsShowArchived')
    return stored === 'true'
  })

  // v2.0: Work units for selected goal
  const [workUnits, setWorkUnits] = useState([])
  const [workUnitsLoading, setWorkUnitsLoading] = useState(false)
  const [approving, setApproving] = useState(false)

  // Context-aware prompt suggestions
  const [suggestedText, setSuggestedText] = useState('')
  const { stats: issueStats } = useIssues({ useWebSocket: !!projectId, pollInterval: projectId ? 30000 : 0 })
  const prompts = useDirectivePrompts(projectId ? issueStats : null)

  const handleSuggestedTextConsumed = useCallback(() => {
    setSuggestedText('')
  }, [])

  // Shared conversation context
  const {
    messages,
    submitting,
    pendingDirective,
    applying,
    lastCreatedGoal,
    submit,
    applyPending,
    rejectPending,
    retryProcessing,
    clear: clearConversation,
  } = useConversationContext()

  // Subscribe to decomposition events for real-time updates
  useEventStream({
    patterns: ['decomposition.*'],
    enabled: !!projectId,
    onEvent: useCallback((event) => {
      // Refresh work units when decomposition changes
      if (selectedGoal && event.goal_id === selectedGoal.goal_id) {
        loadWorkUnits(selectedGoal.goal_id)
      }
    }, [selectedGoal]), // eslint-disable-line react-hooks/exhaustive-deps
  })

  // Load goals list
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
          try {
            progressMap[g.goal_id] = await getGoalProgress(g.goal_id)
          } catch { /* skip */ }
        })
      )
      setGoalProgress(progressMap)
    } catch (err) {
      console.error('Failed to load goals:', err)
    } finally {
      setGoalsLoading(false)
    }
  }, [showArchived, projectId])

  const loadComments = useCallback(async (goalId) => {
    setCommentsLoading(true)
    try {
      const comments = await getGoalComments(goalId)
      setGoalComments(comments.items || comments || [])
    } catch {
      setGoalComments([])
    } finally {
      setCommentsLoading(false)
    }
  }, [])

  // v2.0: Load work units for a goal
  const loadWorkUnits = useCallback(async (goalId) => {
    setWorkUnitsLoading(true)
    try {
      const data = await getWorkUnits(goalId)
      setWorkUnits(data?.work_units || data || [])
    } catch {
      // API not wired yet — expected during migration
      setWorkUnits([])
    } finally {
      setWorkUnitsLoading(false)
    }
  }, [])

  // Clear on project change
  useEffect(() => {
    setSelectedGoal(null)
    setGoalComments([])
    setWorkUnits([])
  }, [projectId])

  useEffect(() => { loadGoals() }, [loadGoals])

  useEffect(() => {
    if (selectedGoal) {
      loadComments(selectedGoal.goal_id)
      loadWorkUnits(selectedGoal.goal_id)
    } else {
      setGoalComments([])
      setWorkUnits([])
    }
  }, [selectedGoal, loadComments, loadWorkUnits])

  // Fetch issues for the selected goal's completion card (v1.0 compat)
  useEffect(() => {
    if (!selectedGoal?.issue_ids?.length) {
      setGoalIssues([])
      return
    }
    let cancelled = false
    setGoalIssuesLoading(true)
    Promise.allSettled(selectedGoal.issue_ids.map(id => getIssue(id)))
      .then(results => {
        if (cancelled) return
        setGoalIssues(
          results
            .filter(r => r.status === 'fulfilled' && r.value)
            .map(r => r.value)
        )
      })
      .finally(() => { if (!cancelled) setGoalIssuesLoading(false) })
    return () => { cancelled = true }
  }, [selectedGoal?.goal_id, selectedGoal?.issue_ids])

  // When conversation creates a goal, refresh the sidebar list
  useEffect(() => {
    if (lastCreatedGoal) {
      loadGoals()
    }
  }, [lastCreatedGoal]) // eslint-disable-line react-hooks/exhaustive-deps

  // Handlers
  const handleSelectGoal = useCallback((goal) => {
    setSelectedGoal(goal)
    setGoalIssues([])
    clearConversation()
  }, [clearConversation])

  const handleBackToNew = useCallback(() => {
    setSelectedGoal(null)
    setGoalComments([])
    setGoalIssues([])
    setWorkUnits([])
    clearConversation()
  }, [clearConversation])

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
        setGoalComments([])
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
        setGoalComments([])
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

  // v2.0: Approve decomposition — transition work units from draft to ready
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

  // Handle input submission: comment on selected goal or create via conversation
  const handleSubmit = useCallback(async (text, mode, options) => {
    if (selectedGoal) {
      setAddingComment(true)
      try {
        const comment = await createGoalComment(selectedGoal.goal_id, {
          content: text,
          ...(options?.priority && { priority: options.priority }),
        })
        setGoalComments(prev => [...prev, comment])
        setGoalCommentCounts(prev => ({
          ...prev,
          [selectedGoal.goal_id]: (prev[selectedGoal.goal_id] || 0) + 1,
        }))
      } catch (err) {
        console.error('Failed to add comment:', err)
      } finally {
        setAddingComment(false)
      }
      return
    }
    await submit(text, mode, options)
  }, [selectedGoal, submit])

  // No project selected
  if (!projectId) {
    return (
      <div className="conv-page">
        <div className="conv-header">
          <div className="conv-header-content">
            <h1>Directives</h1>
            <PageSubtitle>Select a project to get started</PageSubtitle>
          </div>
        </div>
        <EmptyState
          icon={FolderOpen}
          title="Select a Project"
          description="Please select a project from the sidebar to manage directives."
        />
      </div>
    )
  }

  // Check if work units are all in draft (decomposition review mode)
  const hasDraftUnits = workUnits.length > 0 && workUnits.some(u => u.status === 'draft')
  const hasWorkUnits = workUnits.length > 0

  return (
    <div className="conv-page">
      <div className="conv-header">
        <div className="conv-header-content">
          <h1>Directives</h1>
          <PageSubtitle>
            {activeProject ? `Directing ${activeProject.name}` : 'Select a project'}
          </PageSubtitle>
        </div>
        <div className="conv-header-actions">
          {selectedGoal && (
            <button className="conv-new-btn" onClick={handleBackToNew}>
              <Plus size={14} /> New
            </button>
          )}
          {hasDraftUnits && (
            <button
              className="conv-new-btn conv-approve-btn"
              onClick={handleApproveDecomposition}
              disabled={approving}
            >
              <CheckCircle2 size={14} />
              {approving ? 'Approving...' : 'Approve Decomposition'}
            </button>
          )}
        </div>
      </div>

      <div className="conv-layout">
        <div className="conv-main">
          {/* Selected goal header */}
          {selectedGoal && (
            <div className="conv-goal-header">
              {selectedGoal.description ? (
                <>
                  {selectedGoal.title &&
                   selectedGoal.title !== selectedGoal.description &&
                   !selectedGoal.description.startsWith(selectedGoal.title.replace(/\.{3}$/, '')) &&
                   selectedGoal.title.length < 100 && (
                    <h2>{selectedGoal.title}</h2>
                  )}
                  <p>{selectedGoal.description}</p>
                </>
              ) : (
                <h2>{selectedGoal.title}</h2>
              )}
              {selectedGoal.priority && (
                <span className="conv-tag conv-tag-priority">{selectedGoal.priority}</span>
              )}
              {hasWorkUnits && (
                <span className="conv-tag conv-tag-units">
                  <GitBranch size={12} /> {workUnits.length} work units
                </span>
              )}
            </div>
          )}

          {/* Conversation content area */}
          <div className="conv-content">
            {selectedGoal ? (
              commentsLoading && goalIssuesLoading && workUnitsLoading ? (
                <div className="conv-loading"><Spinner size="md" /></div>
              ) : (
                <div className="conv-timeline">
                  {/* v2.0: Work unit decomposition artifact */}
                  {hasWorkUnits && (
                    <WorkUnitList
                      units={workUnits}
                      onSelectUnit={(unit) => {
                        // Could open a detail modal or navigate in the future
                        console.log('Selected unit:', unit.id)
                      }}
                    />
                  )}

                  {/* v1.0 compat: Completion card for goals processed the old way */}
                  {!hasWorkUnits && selectedGoal.issue_ids?.length > 0 && goalIssues.length > 0 && (
                    <GoalCompletionCard
                      issues={goalIssues}
                      reasoning={selectedGoal.decomposition_reasoning}
                      startedAt={selectedGoal.planning_started_at}
                      completedAt={selectedGoal.completed_at}
                    />
                  )}

                  {goalComments.length === 0 && !selectedGoal.issue_ids?.length && !hasWorkUnits && (
                    <div className="conv-empty">
                      <MessageSquare size={32} className="conv-empty-icon" />
                      <p>No comments yet. Add context or adjust priorities below.</p>
                    </div>
                  )}

                  {/* Comments / conversation history */}
                  {goalComments.map((comment) => (
                    <div key={comment.comment_id} className="conv-msg conv-msg-user">
                      <div className="conv-msg-bubble conv-bubble-user">
                        <p className="conv-msg-text">{comment.content}</p>
                        {(comment.priority || comment.area) && (
                          <div className="conv-comment-meta">
                            {comment.priority && (
                              <span className="conv-tag conv-tag-priority">{comment.priority}</span>
                            )}
                          </div>
                        )}
                        <span className="conv-msg-time">
                          {new Date(comment.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )
            ) : (
              // New conversation mode
              <>
                {messages.length === 0 && (
                  <div className="conv-welcome">
                    <MessageSquare size={48} className="conv-welcome-icon" />
                    <h2>What would you like to do?</h2>
                    <p>
                      Describe new work, shift priorities, or ask about status.
                      The system will decompose your goal into independent work units with formal specifications.
                    </p>
                    {prompts.length > 0 && (
                      <div className="conv-prompt-chips">
                        {prompts.map((prompt) => (
                          <button
                            key={prompt.text}
                            className="conv-prompt-chip"
                            onClick={() => setSuggestedText(prompt.text)}
                          >
                            {prompt.label}
                          </button>
                        ))}
                      </div>
                    )}
                    <InlineHint hintKey="directives-how-it-works">
                      Directives are decomposed into formally specified work units with target files, verification criteria,
                      and independence assertions. Review the decomposition, refine via chat, then approve for execution.
                    </InlineHint>
                  </div>
                )}
                <ConversationTimeline
                  messages={messages}
                  pendingDirective={pendingDirective}
                  applying={applying}
                  onApply={applyPending}
                  onReject={rejectPending}
                  onRetry={retryProcessing}
                />
              </>
            )}
          </div>

          {/* Unified input — chat for both new goals and decomposition refinement */}
          <ConversationInput
            onSubmit={handleSubmit}
            submitting={submitting || addingComment}
            disabled={!!pendingDirective && !selectedGoal}
            commentMode={!!selectedGoal}
            placeholder={
              selectedGoal && hasWorkUnits
                ? 'Refine decomposition... (e.g., "split this unit", "these overlap on config.py")'
                : selectedGoal
                  ? 'Add context or adjust priorities...'
                  : undefined
            }
            suggestedText={suggestedText}
            onSuggestedTextConsumed={handleSuggestedTextConsumed}
          />
        </div>

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
