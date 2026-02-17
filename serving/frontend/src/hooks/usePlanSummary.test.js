import { renderHook, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import usePlanSummary from './usePlanSummary'

vi.mock('../api/planSummary', () => ({
  getPlanSummary: vi.fn(),
}))

import { getPlanSummary } from '../api/planSummary'

describe('usePlanSummary', () => {
  beforeEach(() => {
    getPlanSummary.mockReset()
  })

  it('returns null data when no projectId', () => {
    const { result } = renderHook(() => usePlanSummary(null, { pollInterval: 0 }))
    expect(result.current.data).toBeNull()
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBeNull()
    expect(getPlanSummary).not.toHaveBeenCalled()
  })

  it('fetches data on mount', async () => {
    const mockData = { in_progress_count: 2, ready_count: 3, blocked_count: 1 }
    getPlanSummary.mockResolvedValue(mockData)

    const { result } = renderHook(() => usePlanSummary('proj-1', { pollInterval: 0 }))

    await waitFor(() => {
      expect(result.current.data).toEqual(mockData)
    })
    expect(result.current.error).toBeNull()
    expect(getPlanSummary).toHaveBeenCalledWith('proj-1')
  })

  it('handles 503 errors gracefully without setting error', async () => {
    getPlanSummary.mockRejectedValue(new Error('503 Service Unavailable'))

    const { result } = renderHook(() => usePlanSummary('proj-1', { pollInterval: 0 }))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.data).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it('handles "not available" errors gracefully', async () => {
    getPlanSummary.mockRejectedValue(new Error('Plan summary not available'))

    const { result } = renderHook(() => usePlanSummary('proj-1', { pollInterval: 0 }))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBeNull()
  })

  it('sets error for non-503 errors', async () => {
    getPlanSummary.mockRejectedValue(new Error('Network failure'))

    const { result } = renderHook(() => usePlanSummary('proj-1', { pollInterval: 0 }))

    await waitFor(() => {
      expect(result.current.error).toBe('Network failure')
    })
  })

  it('sets up polling interval when pollInterval > 0', async () => {
    getPlanSummary.mockResolvedValue({ in_progress_count: 1 })
    const setIntervalSpy = vi.spyOn(global, 'setInterval')

    const { unmount } = renderHook(() => usePlanSummary('proj-1', { pollInterval: 5000 }))

    await waitFor(() => {
      expect(getPlanSummary).toHaveBeenCalledTimes(1)
    })

    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 5000)
    setIntervalSpy.mockRestore()
    unmount()
  })

  it('cleans up polling on unmount', async () => {
    getPlanSummary.mockResolvedValue({})
    const clearIntervalSpy = vi.spyOn(global, 'clearInterval')

    const { unmount } = renderHook(() => usePlanSummary('proj-1', { pollInterval: 5000 }))

    await waitFor(() => {
      expect(getPlanSummary).toHaveBeenCalledTimes(1)
    })

    unmount()
    expect(clearIntervalSpy).toHaveBeenCalled()
    clearIntervalSpy.mockRestore()
  })

  it('does not set up polling when pollInterval is 0', async () => {
    getPlanSummary.mockResolvedValue({})

    const { result } = renderHook(() => usePlanSummary('proj-1', { pollInterval: 0 }))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    // With pollInterval 0, only the initial fetch should have happened
    // A second fetch should NOT occur (no polling)
    const callCount = getPlanSummary.mock.calls.length
    // Wait a tick to ensure no extra calls arrive
    await new Promise(resolve => setTimeout(resolve, 50))
    expect(getPlanSummary).toHaveBeenCalledTimes(callCount)
  })

  it('refresh callback triggers immediate refetch', async () => {
    getPlanSummary.mockResolvedValue({ in_progress_count: 0 })

    const { result } = renderHook(() => usePlanSummary('proj-1', { pollInterval: 0 }))

    await waitFor(() => {
      expect(getPlanSummary).toHaveBeenCalledTimes(1)
    })

    await act(async () => {
      await result.current.refresh()
    })

    expect(getPlanSummary).toHaveBeenCalledTimes(2)
  })
})
