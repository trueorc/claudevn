import { useState, useCallback, useEffect, useRef } from 'react'
import { autoProcessGoal, getProcessingStatus } from '../api/goals'

/**
 * Workflow steps for goal processing.
 */
export const WORKFLOW_STEPS = {
  INPUT: 'input',
  PROCESSING: 'processing',
  COMPLETE: 'complete'
}

/**
 * Processing stages from backend (mirrors ProcessingStage enum).
 */
export const PROCESSING_STAGES = {
  QUEUED: 'queued',
  DECOMPOSING: 'decomposing',
  CHARACTERIZING: 'characterizing',
  CREATING_ISSUES: 'creating_issues',
  COMPLETE: 'complete',
  FAILED: 'failed'
}

export const POLL_CONFIG = {
  INITIAL_INTERVAL_MS: 2000,
  MAX_INTERVAL_MS: 30000,
  BACKOFF_MULTIPLIER: 1.5,
  TIMEOUT_MS: 5 * 60 * 1000,          // 5 minutes
  STALL_THRESHOLD_MS: 2 * 60 * 1000,  // 2 minutes same stage
  MAX_CONSECUTIVE_ERRORS: 5,
}

/**
 * Hook for managing goal auto-process workflow with backend polling.
 * Features exponential backoff, timeout, stall detection, and error recovery.
 */
function useGoals() {
  const [step, setStep] = useState(WORKFLOW_STEPS.INPUT)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [executionResult, setExecutionResult] = useState(null)
  const [processingStage, setProcessingStage] = useState(null)
  const [processingStartedAt, setProcessingStartedAt] = useState(null)
  const [isTimedOut, setIsTimedOut] = useState(false)
  const [isStalled, setIsStalled] = useState(false)

  const pollTimeoutRef = useRef(null)
  const currentGoalIdRef = useRef(null)
  const pollingStartRef = useRef(null)
  const lastStageChangeRef = useRef(null)
  const lastStageRef = useRef(null)
  const consecutiveErrorsRef = useRef(0)

  /**
   * Stop polling for processing status.
   */
  const stopPolling = useCallback(() => {
    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current)
      pollTimeoutRef.current = null
    }
  }, [])

  /**
   * Start polling for processing status with exponential backoff.
   */
  const startPolling = useCallback((goalId) => {
    stopPolling()
    currentGoalIdRef.current = goalId
    pollingStartRef.current = Date.now()
    lastStageChangeRef.current = Date.now()
    lastStageRef.current = null
    consecutiveErrorsRef.current = 0
    setIsTimedOut(false)
    setIsStalled(false)

    const schedulePoll = (interval) => {
      pollTimeoutRef.current = setTimeout(async () => {
        const elapsed = Date.now() - pollingStartRef.current

        // Check timeout
        if (elapsed >= POLL_CONFIG.TIMEOUT_MS) {
          stopPolling()
          setIsTimedOut(true)
          setLoading(false)
          return
        }

        // Check stall (same stage for too long)
        const sinceStageChange = Date.now() - lastStageChangeRef.current
        if (sinceStageChange >= POLL_CONFIG.STALL_THRESHOLD_MS) {
          setIsStalled(true)
        }

        try {
          const status = await getProcessingStatus(goalId)
          consecutiveErrorsRef.current = 0

          // Track stage changes for stall detection
          if (status.stage !== lastStageRef.current) {
            lastStageRef.current = status.stage
            lastStageChangeRef.current = Date.now()
            setIsStalled(false)
          }

          setProcessingStage(status.stage)

          if (status.started_at) {
            setProcessingStartedAt(status.started_at)
          }

          if (status.stage === PROCESSING_STAGES.COMPLETE) {
            stopPolling()
            setExecutionResult(status.result)
            setStep(WORKFLOW_STEPS.COMPLETE)
            setLoading(false)
            return
          } else if (status.stage === PROCESSING_STAGES.FAILED) {
            stopPolling()
            setError(status.error || 'Processing failed')
            setStep(WORKFLOW_STEPS.INPUT)
            setLoading(false)
            return
          }
        } catch (err) {
          // 404 means no processing status — might have completed and expired
          if (err.message?.includes('404')) {
            stopPolling()
            setStep(WORKFLOW_STEPS.INPUT)
            setLoading(false)
            return
          }
          consecutiveErrorsRef.current++
          if (consecutiveErrorsRef.current >= POLL_CONFIG.MAX_CONSECUTIVE_ERRORS) {
            stopPolling()
            setError('Unable to reach server after multiple attempts')
            setStep(WORKFLOW_STEPS.INPUT)
            setLoading(false)
            return
          }
        }

        // Schedule next poll with backoff
        const nextInterval = Math.min(
          interval * POLL_CONFIG.BACKOFF_MULTIPLIER,
          POLL_CONFIG.MAX_INTERVAL_MS
        )
        schedulePoll(nextInterval)
      }, interval)
    }

    schedulePoll(POLL_CONFIG.INITIAL_INTERVAL_MS)
  }, [stopPolling])

  // Clean up polling on unmount
  useEffect(() => {
    return () => stopPolling()
  }, [stopPolling])

  /**
   * Auto-process a goal: fires async request, then polls for status.
   */
  const autoProcess = useCallback(async (goalIdToProcess, constraints = null) => {
    setLoading(true)
    setError(null)
    setStep(WORKFLOW_STEPS.PROCESSING)
    setProcessingStage(PROCESSING_STAGES.QUEUED)
    setProcessingStartedAt(new Date().toISOString())
    setIsTimedOut(false)
    setIsStalled(false)

    try {
      await autoProcessGoal(goalIdToProcess, constraints)
      // 202 returned — start polling for progress
      startPolling(goalIdToProcess)
    } catch (err) {
      // Synchronous validation errors (400, 404) come back immediately
      setError(err.message)
      setStep(WORKFLOW_STEPS.INPUT)
      setLoading(false)
      throw err
    }
  }, [startPolling])

  /**
   * Resume polling for a goal that's already processing (e.g. after page refresh
   * or when the backend has already started processing via unified directives).
   */
  const resumePolling = useCallback((goalId, initialStage = PROCESSING_STAGES.DECOMPOSING) => {
    setStep(WORKFLOW_STEPS.PROCESSING)
    setLoading(true)
    setError(null)
    setProcessingStage(initialStage)
    setProcessingStartedAt(new Date().toISOString())
    setIsTimedOut(false)
    setIsStalled(false)
    startPolling(goalId)
  }, [startPolling])

  /**
   * Retry processing for the current goal after timeout or stall.
   */
  const retryProcessing = useCallback(async () => {
    const goalId = currentGoalIdRef.current
    if (!goalId) return

    setIsTimedOut(false)
    setIsStalled(false)
    setError(null)
    setLoading(true)
    setStep(WORKFLOW_STEPS.PROCESSING)
    setProcessingStage(PROCESSING_STAGES.QUEUED)
    setProcessingStartedAt(new Date().toISOString())

    try {
      await autoProcessGoal(goalId)
      startPolling(goalId)
    } catch (err) {
      setError(err.message)
      setStep(WORKFLOW_STEPS.INPUT)
      setLoading(false)
    }
  }, [startPolling])

  /**
   * Reset the workflow to start over.
   */
  const reset = useCallback(() => {
    stopPolling()
    setStep(WORKFLOW_STEPS.INPUT)
    setLoading(false)
    setError(null)
    setExecutionResult(null)
    setProcessingStage(null)
    setProcessingStartedAt(null)
    setIsTimedOut(false)
    setIsStalled(false)
    currentGoalIdRef.current = null
  }, [stopPolling])

  return {
    // State
    step,
    loading,
    error,
    executionResult,
    processingStage,
    processingStartedAt,
    isTimedOut,
    isStalled,

    // Actions
    autoProcess,
    resumePolling,
    retryProcessing,
    reset,

    // Helpers
    isInputStep: step === WORKFLOW_STEPS.INPUT,
    isProcessing: step === WORKFLOW_STEPS.PROCESSING,
    isComplete: step === WORKFLOW_STEPS.COMPLETE
  }
}

export default useGoals
