import { renderHook, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import useCharacterizationStatuses from './useCharacterizationStatuses'

vi.mock('../api/characterization', () => ({
  getCharacterizationStatuses: vi.fn(),
}))

import { getCharacterizationStatuses } from '../api/characterization'

describe('useCharacterizationStatuses', () => {
  beforeEach(() => {
    getCharacterizationStatuses.mockReset()
  })

  it('returns empty map when no projectId', () => {
    const { result } = renderHook(() => useCharacterizationStatuses(null, { pollInterval: 0 }))
    expect(result.current.statusMap).toEqual({})
    expect(result.current.loading).toBe(false)
  })

  it('fetches and builds status map from API response', async () => {
    getCharacterizationStatuses.mockResolvedValue({
      results: [
        { item_id: 'issue-1', status: 'completed', ontology_tags: { universal: { work_type: 'feature' } } },
        { item_id: 'issue-2', status: 'pending', ontology_tags: null },
      ],
    })

    const { result } = renderHook(() => useCharacterizationStatuses('proj-1', { pollInterval: 0 }))

    await waitFor(() => {
      expect(result.current.statusMap['issue-1']).toEqual({
        status: 'completed',
        ontology_tags: { universal: { work_type: 'feature' } },
      })
    })

    expect(result.current.statusMap['issue-2']).toEqual({
      status: 'pending',
      ontology_tags: null,
    })
    expect(getCharacterizationStatuses).toHaveBeenCalledWith('proj-1')
  })

  it('reports hasPending when in_progress items exist', async () => {
    getCharacterizationStatuses.mockResolvedValue({
      results: [
        { item_id: 'issue-1', status: 'in_progress', ontology_tags: null },
      ],
    })

    const { result } = renderHook(() => useCharacterizationStatuses('proj-1', { pollInterval: 0 }))

    await waitFor(() => {
      expect(result.current.hasPending).toBe(true)
    })
  })

  it('reports hasPending false when all completed', async () => {
    getCharacterizationStatuses.mockResolvedValue({
      results: [
        { item_id: 'issue-1', status: 'completed', ontology_tags: {} },
      ],
    })

    const { result } = renderHook(() => useCharacterizationStatuses('proj-1', { pollInterval: 0 }))

    await waitFor(() => {
      expect(result.current.hasPending).toBe(false)
      expect(Object.keys(result.current.statusMap).length).toBe(1)
    })
  })

  it('handles API errors gracefully', async () => {
    getCharacterizationStatuses.mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => useCharacterizationStatuses('proj-1', { pollInterval: 0 }))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.statusMap).toEqual({})
  })

  it('calls refresh function to reload data', async () => {
    getCharacterizationStatuses.mockResolvedValue({ results: [] })

    const { result } = renderHook(() => useCharacterizationStatuses('proj-1', { pollInterval: 0 }))

    await waitFor(() => {
      expect(getCharacterizationStatuses).toHaveBeenCalledTimes(1)
    })

    await act(async () => {
      await result.current.refresh()
    })

    expect(getCharacterizationStatuses).toHaveBeenCalledTimes(2)
  })
})
