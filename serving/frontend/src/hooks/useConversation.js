import { useState, useCallback, useEffect, useRef } from 'react'
import { createGoal } from '../api/workmap'
import { interpretDirective, applyDirective, rejectDirective } from '../api/directives'
import useGoals, { WORKFLOW_STEPS, PROCESSING_STAGES } from './useGoals'

export const MSG_TYPES = {
  USER: 'user',
  THINKING: 'thinking',
  GOAL_CREATED: 'goal_created',
  GOAL_PROCESSING: 'goal_processing',
  GOAL_COMPLETE: 'goal_complete',
  DIRECTIVE_PREVIEW: 'directive_preview',
  DIRECTIVE_APPLIED: 'directive_applied',
  DIRECTIVE_REJECTED: 'directive_rejected',
  ERROR: 'error',
}

export const INTENT_MODES = {
  AUTO: 'auto',
  NEW_WORK: 'new_work',
  DIRECTIVE: 'directive',
}

export { PROCESSING_STAGES }

let nextMsgId = 1

export default function useConversation(projectId) {
  const [messages, setMessages] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [pendingDirective, setPendingDirective] = useState(null)
  const [applying, setApplying] = useState(false)
  const [lastCreatedGoal, setLastCreatedGoal] = useState(null)
  const goalCompleteHandled = useRef(false)

  const {
    step,
    error: goalError,
    executionResult,
    processingStage,
    processingStartedAt,
    isTimedOut,
    isStalled,
    autoProcess,
    resumePolling,
    retryProcessing,
    reset: resetGoals,
  } = useGoals()

  // Clear everything on project change
  useEffect(() => {
    setMessages([])
    setPendingDirective(null)
    setLastCreatedGoal(null)
    goalCompleteHandled.current = false
    resetGoals()
  }, [projectId, resetGoals])

  const addMsg = useCallback((type, content, meta = {}) => {
    const msg = {
      id: nextMsgId++,
      type,
      content,
      timestamp: new Date().toISOString(),
      ...meta,
    }
    setMessages(prev => [...prev, msg])
    return msg
  }, [])

  const removeByType = useCallback((type) => {
    setMessages(prev => prev.filter(m => m.type !== type))
  }, [])

  // Update processing stage in the timeline
  useEffect(() => {
    if (step === WORKFLOW_STEPS.PROCESSING && processingStage) {
      setMessages(prev => {
        const idx = prev.findLastIndex(m => m.type === MSG_TYPES.GOAL_PROCESSING)
        if (idx >= 0) {
          const updated = [...prev]
          updated[idx] = {
            ...updated[idx],
            stage: processingStage,
            startedAt: processingStartedAt,
            isStalled,
            isTimedOut,
          }
          return updated
        }
        return prev
      })
    }
  }, [step, processingStage, processingStartedAt, isStalled, isTimedOut])

  // Handle goal processing completion — transform in-place instead of remove+add
  useEffect(() => {
    if (step === WORKFLOW_STEPS.COMPLETE && executionResult && !goalCompleteHandled.current) {
      goalCompleteHandled.current = true
      setMessages(prev => prev.map(m =>
        m.type === MSG_TYPES.GOAL_PROCESSING
          ? {
              ...m,
              type: MSG_TYPES.GOAL_COMPLETE,
              stage: 'complete',
              content: 'Work items created',
              result: executionResult,
              goal: lastCreatedGoal,
            }
          : m
      ))
    }
  }, [step, executionResult, lastCreatedGoal])

  // Handle goal processing errors
  useEffect(() => {
    if (goalError) {
      removeByType(MSG_TYPES.GOAL_PROCESSING)
      removeByType(MSG_TYPES.THINKING)
      addMsg(MSG_TYPES.ERROR, goalError)
    }
  }, [goalError, addMsg, removeByType])

  const submit = useCallback(async (text, mode = INTENT_MODES.AUTO, options = {}) => {
    if (!projectId || !text.trim() || submitting) return null
    setSubmitting(true)
    goalCompleteHandled.current = false
    const trimmed = text.trim()

    addMsg(MSG_TYPES.USER, trimmed, { mode, ...options })

    try {
      if (mode === INTENT_MODES.DIRECTIVE) {
        const thinkingId = addMsg(MSG_TYPES.THINKING, 'Interpreting directive...').id
        const directive = await interpretDirective(trimmed, projectId)
        setMessages(prev => prev.filter(m => m.id !== thinkingId))
        setPendingDirective(directive)
        addMsg(MSG_TYPES.DIRECTIVE_PREVIEW, 'Here\'s what I understood:', { directive })
        return { type: 'directive', directive }
      }

      if (mode === INTENT_MODES.NEW_WORK) {
        const thinkingId = addMsg(MSG_TYPES.THINKING, 'Creating work item...').id
        const goal = await createGoal({
          title: trimmed.slice(0, 500),
          description: trimmed,
          priority: options.priority || 'P2',
          project_id: projectId,
          ...(options.area && { area: options.area }),
          ...(options.tags?.length > 0 && { tags: options.tags }),
        })
        setMessages(prev => prev.filter(m => m.id !== thinkingId))
        setLastCreatedGoal(goal)
        addMsg(MSG_TYPES.GOAL_CREATED, `Created: ${goal.title}`, { goal })
        addMsg(MSG_TYPES.GOAL_PROCESSING, 'Analyzing and decomposing...', { stage: 'queued' })
        await autoProcess(goal.goal_id)
        return { type: 'goal', goal }
      }

      // Auto mode: try directive interpretation first
      const thinkingId = addMsg(MSG_TYPES.THINKING, 'Understanding your intent...').id
      try {
        const directive = await interpretDirective(trimmed, projectId)
        const hasAdjustments =
          directive?.interpretation?.weight_adjustments?.length > 0 ||
          directive?.interpretation?.policy_adjustments?.length > 0

        if (hasAdjustments) {
          setMessages(prev => prev.filter(m => m.id !== thinkingId))
          setPendingDirective(directive)
          addMsg(MSG_TYPES.DIRECTIVE_PREVIEW, 'I interpreted this as a topology directive:', { directive })
          return { type: 'directive', directive }
        }

        // Backend already created a goal for new_work directives — use it.
        // The unified directive service already started auto-processing in the
        // background, so we only need to poll for status (not POST again).
        const backendGoalId = directive?.outcome?.goal_id_created
        if (backendGoalId) {
          setMessages(prev => prev.filter(m => m.id !== thinkingId))
          const goal = {
            goal_id: backendGoalId,
            title: directive.text?.slice(0, 200) || trimmed.slice(0, 200),
            description: directive.text || trimmed,
          }
          setLastCreatedGoal(goal)
          addMsg(MSG_TYPES.GOAL_CREATED, `Created: ${goal.title}`, { goal })
          addMsg(MSG_TYPES.GOAL_PROCESSING, 'Analyzing and decomposing...', { stage: 'queued' })
          resumePolling(backendGoalId, 'queued')
          return { type: 'goal', goal }
        }
      } catch {
        // Directive interpretation failed — fall through to goal creation
      }

      // No directive adjustments and no backend goal → create as goal
      setMessages(prev => prev.filter(m => m.id !== thinkingId))
      const goalThinkingId = addMsg(MSG_TYPES.THINKING, 'Creating as new work...').id
      const goal = await createGoal({
        title: trimmed.slice(0, 500),
        description: trimmed,
        priority: options.priority || 'P2',
        project_id: projectId,
      })
      setMessages(prev => prev.filter(m => m.id !== goalThinkingId))
      setLastCreatedGoal(goal)
      addMsg(MSG_TYPES.GOAL_CREATED, `Created: ${goal.title}`, { goal })
      addMsg(MSG_TYPES.GOAL_PROCESSING, 'Analyzing and decomposing...', { stage: 'queued' })
      await autoProcess(goal.goal_id)
      return { type: 'goal', goal }
    } catch (err) {
      removeByType(MSG_TYPES.THINKING)
      addMsg(MSG_TYPES.ERROR, err.message || 'Something went wrong')
      return null
    } finally {
      setSubmitting(false)
    }
  }, [projectId, submitting, addMsg, removeByType, autoProcess, resumePolling])

  const applyPending = useCallback(async () => {
    if (!pendingDirective || !projectId || applying) return
    setApplying(true)
    try {
      const result = await applyDirective(pendingDirective.directive_id, projectId)
      const appliedId = pendingDirective.directive_id
      setPendingDirective(null)
      setMessages(prev => prev.map(m =>
        m.type === MSG_TYPES.DIRECTIVE_PREVIEW && m.directive?.directive_id === appliedId
          ? { ...m, type: MSG_TYPES.DIRECTIVE_APPLIED, content: 'Changes applied successfully', applied: true }
          : m
      ))
      return result
    } catch (err) {
      addMsg(MSG_TYPES.ERROR, err.message || 'Failed to apply changes')
      return null
    } finally {
      setApplying(false)
    }
  }, [pendingDirective, projectId, applying, addMsg])

  const rejectPending = useCallback(async () => {
    if (!pendingDirective || !projectId) return
    try {
      const rejectedId = pendingDirective.directive_id
      await rejectDirective(rejectedId, projectId)
      setPendingDirective(null)
      setMessages(prev => prev.map(m =>
        m.type === MSG_TYPES.DIRECTIVE_PREVIEW && m.directive?.directive_id === rejectedId
          ? { ...m, type: MSG_TYPES.DIRECTIVE_REJECTED, content: 'Changes rejected', rejected: true }
          : m
      ))
    } catch (err) {
      addMsg(MSG_TYPES.ERROR, err.message || 'Failed to reject changes')
    }
  }, [pendingDirective, projectId, addMsg])

  const clear = useCallback(() => {
    setMessages([])
    setPendingDirective(null)
    setLastCreatedGoal(null)
    goalCompleteHandled.current = false
    resetGoals()
  }, [resetGoals])

  return {
    messages,
    submitting,
    pendingDirective,
    applying,
    lastCreatedGoal,
    submit,
    applyPending,
    rejectPending,
    retryProcessing,
    clear,
  }
}
