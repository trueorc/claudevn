import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import useGoals, { WORKFLOW_STEPS, PROCESSING_STAGES, POLL_CONFIG } from './useGoals'

vi.mock('../api/goals', () => ({
  autoProcessGoal: vi.fn(),
  getProcessingStatus: vi.fn(),
}))

import { autoProcessGoal, getProcessingStatus } from '../api/goals'

describe('useGoals', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    autoProcessGoal.mockResolvedValue({ status: 'accepted' })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts in INPUT step', () => {
    const { result } = renderHook(() => useGoals())
    expect(result.current.step).toBe(WORKFLOW_STEPS.INPUT)
    expect(result.current.loading).toBe(false)
    expect(result.current.isTimedOut).toBe(false)
    expect(result.current.isStalled).toBe(false)
  })

  it('transitions to PROCESSING on autoProcess', async () => {
    getProcessingStatus.mockResolvedValue({ stage: 'queued' })
    const { result } = renderHook(() => useGoals())

    await act(async () => {
      await result.current.autoProcess('goal-1')
    })

    expect(result.current.step).toBe(WORKFLOW_STEPS.PROCESSING)
    expect(result.current.loading).toBe(true)
    expect(result.current.processingStage).toBe(PROCESSING_STAGES.QUEUED)
  })

  it('uses exponential backoff for polling intervals', async () => {
    getProcessingStatus.mockResolvedValue({ stage: 'decomposing' })
    const { result } = renderHook(() => useGoals())

    await act(async () => {
      await result.current.autoProcess('goal-1')
    })

    // First poll at INITIAL_INTERVAL_MS (2000ms)
    await act(async () => {
      vi.advanceTimersByTime(POLL_CONFIG.INITIAL_INTERVAL_MS)
    })
    expect(getProcessingStatus).toHaveBeenCalledTimes(1)

    // Second poll at 2000 * 1.5 = 3000ms
    await act(async () => {
      vi.advanceTimersByTime(3000)
    })
    expect(getProcessingStatus).toHaveBeenCalledTimes(2)

    // Third poll at 3000 * 1.5 = 4500ms
    await act(async () => {
      vi.advanceTimersByTime(4500)
    })
    expect(getProcessingStatus).toHaveBeenCalledTimes(3)
  })

  it('caps polling interval at MAX_INTERVAL_MS', async () => {
    getProcessingStatus.mockResolvedValue({ stage: 'decomposing' })
    const { result } = renderHook(() => useGoals())

    await act(async () => {
      await result.current.autoProcess('goal-1')
    })

    // Advance through several backoff cycles to reach the cap
    // 2000, 3000, 4500, 6750, 10125, 15187, 22781, 30000 (capped)
    let elapsed = 0
    let interval = POLL_CONFIG.INITIAL_INTERVAL_MS
    for (let i = 0; i < 8; i++) {
      await act(async () => {
        vi.advanceTimersByTime(interval)
      })
      elapsed += interval
      interval = Math.min(interval * POLL_CONFIG.BACKOFF_MULTIPLIER, POLL_CONFIG.MAX_INTERVAL_MS)
    }

    const callCount = getProcessingStatus.mock.calls.length

    // Next two polls should both be at MAX_INTERVAL_MS
    await act(async () => {
      vi.advanceTimersByTime(POLL_CONFIG.MAX_INTERVAL_MS)
    })
    expect(getProcessingStatus).toHaveBeenCalledTimes(callCount + 1)

    await act(async () => {
      vi.advanceTimersByTime(POLL_CONFIG.MAX_INTERVAL_MS)
    })
    expect(getProcessingStatus).toHaveBeenCalledTimes(callCount + 2)
  })

  it('stops polling and completes on COMPLETE stage', async () => {
    getProcessingStatus.mockResolvedValue({
      stage: 'complete',
      result: { issues_created: [{ title: 'Task 1' }] },
    })
    const { result } = renderHook(() => useGoals())

    await act(async () => {
      await result.current.autoProcess('goal-1')
    })

    await act(async () => {
      vi.advanceTimersByTime(POLL_CONFIG.INITIAL_INTERVAL_MS)
    })

    expect(result.current.step).toBe(WORKFLOW_STEPS.COMPLETE)
    expect(result.current.loading).toBe(false)
    expect(result.current.executionResult).toEqual({ issues_created: [{ title: 'Task 1' }] })
  })

  it('stops polling and sets error on FAILED stage', async () => {
    getProcessingStatus.mockResolvedValue({
      stage: 'failed',
      error: 'Decomposition failed',
    })
    const { result } = renderHook(() => useGoals())

    await act(async () => {
      await result.current.autoProcess('goal-1')
    })

    await act(async () => {
      vi.advanceTimersByTime(POLL_CONFIG.INITIAL_INTERVAL_MS)
    })

    expect(result.current.step).toBe(WORKFLOW_STEPS.INPUT)
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBe('Decomposition failed')
  })

  it('times out after TIMEOUT_MS and sets isTimedOut', async () => {
    getProcessingStatus.mockResolvedValue({ stage: 'decomposing' })
    const { result } = renderHook(() => useGoals())

    await act(async () => {
      await result.current.autoProcess('goal-1')
    })

    // Advance time past the timeout threshold
    // We need to advance through each polling interval to trigger the timeout check
    let elapsed = 0
    let interval = POLL_CONFIG.INITIAL_INTERVAL_MS
    while (elapsed < POLL_CONFIG.TIMEOUT_MS + POLL_CONFIG.MAX_INTERVAL_MS) {
      await act(async () => {
        vi.advanceTimersByTime(interval)
      })
      elapsed += interval
      interval = Math.min(interval * POLL_CONFIG.BACKOFF_MULTIPLIER, POLL_CONFIG.MAX_INTERVAL_MS)
    }

    expect(result.current.isTimedOut).toBe(true)
    expect(result.current.loading).toBe(false)
  })

  it('detects stalled state when stage does not change', async () => {
    getProcessingStatus.mockResolvedValue({ stage: 'decomposing' })
    const { result } = renderHook(() => useGoals())

    await act(async () => {
      await result.current.autoProcess('goal-1')
    })

    // Advance past stall threshold while stage stays the same
    let elapsed = 0
    let interval = POLL_CONFIG.INITIAL_INTERVAL_MS
    while (elapsed < POLL_CONFIG.STALL_THRESHOLD_MS + POLL_CONFIG.MAX_INTERVAL_MS) {
      await act(async () => {
        vi.advanceTimersByTime(interval)
      })
      elapsed += interval
      interval = Math.min(interval * POLL_CONFIG.BACKOFF_MULTIPLIER, POLL_CONFIG.MAX_INTERVAL_MS)
    }

    expect(result.current.isStalled).toBe(true)
  })

  it('clears stalled state when stage changes', async () => {
    let callCount = 0
    getProcessingStatus.mockImplementation(async () => {
      callCount++
      // Change stage after several polls
      if (callCount > 6) return { stage: 'creating_issues' }
      return { stage: 'decomposing' }
    })
    const { result } = renderHook(() => useGoals())

    await act(async () => {
      await result.current.autoProcess('goal-1')
    })

    // Advance past stall threshold
    let elapsed = 0
    let interval = POLL_CONFIG.INITIAL_INTERVAL_MS
    while (elapsed < POLL_CONFIG.STALL_THRESHOLD_MS + POLL_CONFIG.MAX_INTERVAL_MS) {
      await act(async () => {
        vi.advanceTimersByTime(interval)
      })
      elapsed += interval
      interval = Math.min(interval * POLL_CONFIG.BACKOFF_MULTIPLIER, POLL_CONFIG.MAX_INTERVAL_MS)
    }

    // After stage change, isStalled should be cleared
    expect(result.current.isStalled).toBe(false)
    expect(result.current.processingStage).toBe('creating_issues')
  })

  it('stops polling after MAX_CONSECUTIVE_ERRORS', async () => {
    getProcessingStatus.mockRejectedValue(new Error('Network error'))
    const { result } = renderHook(() => useGoals())

    await act(async () => {
      await result.current.autoProcess('goal-1')
    })

    // Trigger enough polls to hit the error limit
    let interval = POLL_CONFIG.INITIAL_INTERVAL_MS
    for (let i = 0; i < POLL_CONFIG.MAX_CONSECUTIVE_ERRORS; i++) {
      await act(async () => {
        vi.advanceTimersByTime(interval)
      })
      interval = Math.min(interval * POLL_CONFIG.BACKOFF_MULTIPLIER, POLL_CONFIG.MAX_INTERVAL_MS)
    }

    expect(result.current.error).toBe('Unable to reach server after multiple attempts')
    expect(result.current.step).toBe(WORKFLOW_STEPS.INPUT)
    expect(result.current.loading).toBe(false)
  })

  it('stops polling on 404 error', async () => {
    getProcessingStatus.mockRejectedValue(new Error('Request failed: 404'))
    const { result } = renderHook(() => useGoals())

    await act(async () => {
      await result.current.autoProcess('goal-1')
    })

    await act(async () => {
      vi.advanceTimersByTime(POLL_CONFIG.INITIAL_INTERVAL_MS)
    })

    expect(result.current.step).toBe(WORKFLOW_STEPS.INPUT)
    expect(result.current.loading).toBe(false)
    // Only one call - should not continue polling after 404
    expect(getProcessingStatus).toHaveBeenCalledTimes(1)
  })

  it('retryProcessing restarts the whole flow', async () => {
    // First: start and timeout
    getProcessingStatus.mockResolvedValue({ stage: 'decomposing' })
    const { result } = renderHook(() => useGoals())

    await act(async () => {
      await result.current.autoProcess('goal-1')
    })

    // Advance to timeout
    let elapsed = 0
    let interval = POLL_CONFIG.INITIAL_INTERVAL_MS
    while (elapsed < POLL_CONFIG.TIMEOUT_MS + POLL_CONFIG.MAX_INTERVAL_MS) {
      await act(async () => {
        vi.advanceTimersByTime(interval)
      })
      elapsed += interval
      interval = Math.min(interval * POLL_CONFIG.BACKOFF_MULTIPLIER, POLL_CONFIG.MAX_INTERVAL_MS)
    }

    expect(result.current.isTimedOut).toBe(true)

    // Now retry - should complete this time
    autoProcessGoal.mockResolvedValue({ status: 'accepted' })
    getProcessingStatus.mockResolvedValue({
      stage: 'complete',
      result: { issues_created: [] },
    })

    await act(async () => {
      await result.current.retryProcessing()
    })

    expect(result.current.isTimedOut).toBe(false)
    expect(result.current.step).toBe(WORKFLOW_STEPS.PROCESSING)
    expect(autoProcessGoal).toHaveBeenCalledWith('goal-1')

    // Complete after first poll
    await act(async () => {
      vi.advanceTimersByTime(POLL_CONFIG.INITIAL_INTERVAL_MS)
    })

    expect(result.current.step).toBe(WORKFLOW_STEPS.COMPLETE)
  })

  it('resumePolling sets state and starts polling without POST', async () => {
    getProcessingStatus.mockResolvedValue({ stage: 'decomposing' })
    const { result } = renderHook(() => useGoals())

    act(() => {
      result.current.resumePolling('goal-1', 'queued')
    })

    // Should be in processing state with the initial stage we passed
    expect(result.current.step).toBe(WORKFLOW_STEPS.PROCESSING)
    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBeNull()
    expect(result.current.processingStage).toBe(PROCESSING_STAGES.QUEUED)
    expect(result.current.processingStartedAt).toBeTruthy()
    expect(result.current.isTimedOut).toBe(false)
    expect(result.current.isStalled).toBe(false)

    // Should NOT have called autoProcessGoal (no POST request)
    expect(autoProcessGoal).not.toHaveBeenCalled()

    // First poll should pick up the actual stage from backend
    await act(async () => {
      vi.advanceTimersByTime(POLL_CONFIG.INITIAL_INTERVAL_MS)
    })
    expect(getProcessingStatus).toHaveBeenCalledWith('goal-1')
    expect(result.current.processingStage).toBe('decomposing')
  })

  it('resumePolling defaults to DECOMPOSING stage', () => {
    const { result } = renderHook(() => useGoals())

    act(() => {
      result.current.resumePolling('goal-1')
    })

    expect(result.current.processingStage).toBe(PROCESSING_STAGES.DECOMPOSING)
  })

  it('reset clears all state', async () => {
    getProcessingStatus.mockResolvedValue({ stage: 'decomposing' })
    const { result } = renderHook(() => useGoals())

    await act(async () => {
      await result.current.autoProcess('goal-1')
    })

    act(() => {
      result.current.reset()
    })

    expect(result.current.step).toBe(WORKFLOW_STEPS.INPUT)
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBeNull()
    expect(result.current.isTimedOut).toBe(false)
    expect(result.current.isStalled).toBe(false)
    expect(result.current.processingStage).toBeNull()
  })

  it('cleans up timeout on unmount', async () => {
    getProcessingStatus.mockResolvedValue({ stage: 'decomposing' })
    const { result, unmount } = renderHook(() => useGoals())

    await act(async () => {
      await result.current.autoProcess('goal-1')
    })

    unmount()

    // Advancing timers should not cause additional calls
    const callsBefore = getProcessingStatus.mock.calls.length
    await act(async () => {
      vi.advanceTimersByTime(POLL_CONFIG.INITIAL_INTERVAL_MS * 10)
    })
    expect(getProcessingStatus.mock.calls.length).toBe(callsBefore)
  })

  it('handles autoProcess validation error without starting polling', async () => {
    autoProcessGoal.mockRejectedValue(new Error('Goal not found'))
    const { result } = renderHook(() => useGoals())

    let caught
    await act(async () => {
      try {
        await result.current.autoProcess('bad-id')
      } catch (err) {
        caught = err
      }
    })

    expect(caught.message).toBe('Goal not found')
    expect(result.current.step).toBe(WORKFLOW_STEPS.INPUT)
    expect(result.current.error).toBe('Goal not found')
    expect(result.current.loading).toBe(false)
  })

  it('exports POLL_CONFIG for external use', () => {
    expect(POLL_CONFIG.INITIAL_INTERVAL_MS).toBe(2000)
    expect(POLL_CONFIG.MAX_INTERVAL_MS).toBe(30000)
    expect(POLL_CONFIG.BACKOFF_MULTIPLIER).toBe(1.5)
    expect(POLL_CONFIG.TIMEOUT_MS).toBe(300000)
    expect(POLL_CONFIG.STALL_THRESHOLD_MS).toBe(120000)
    expect(POLL_CONFIG.MAX_CONSECUTIVE_ERRORS).toBe(5)
  })
})
