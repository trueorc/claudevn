import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import useBucketTree from './useBucketTree'

vi.mock('../api/workmap', () => ({
  getBucketTree: vi.fn(),
}))

import { getBucketTree } from '../api/workmap'

// Mock matches the real API response shape: { project_id, tree: {...}, summary }
const mockApiResponse = {
  project_id: 'proj_1',
  tree: {
    tree_id: 'tree_1',
    project_id: 'proj_1',
    buckets: [
      {
        bucket_id: 'bucket_1',
        rank: 1,
        definition: {
          name: 'Critical Fixes',
          description: 'Urgent production issues',
        },
        items: [
          { item_id: 'issue_aaa', readiness: 'ready', priority_score: 0.9 },
          { item_id: 'issue_bbb', readiness: 'blocked', priority_score: 0.5 },
        ],
      },
      {
        bucket_id: 'bucket_2',
        rank: 2,
        definition: {
          name: 'Feature Work',
          description: 'New features',
        },
        items: [
          { item_id: 'issue_ccc', readiness: 'ready', priority_score: 0.7 },
        ],
      },
    ],
  },
  summary: {
    total_buckets: 2,
    total_items: 3,
    total_ready: 2,
    version: 1,
  },
}

describe('useBucketTree', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getBucketTree.mockResolvedValue(mockApiResponse)
  })

  it('returns empty state when no projectId', async () => {
    const { result } = renderHook(() => useBucketTree(null))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.bucketTree).toBeNull()
    expect(result.current.buckets).toEqual([])
    expect(result.current.itemBucketMap).toEqual({})
    expect(getBucketTree).not.toHaveBeenCalled()
  })

  it('fetches bucket tree data on mount', async () => {
    const { result } = renderHook(() => useBucketTree('proj_1'))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(getBucketTree).toHaveBeenCalledWith('proj_1')
    expect(result.current.bucketTree).toEqual(mockApiResponse)
    expect(result.current.buckets).toHaveLength(2)
  })

  it('builds itemBucketMap correctly', async () => {
    const { result } = renderHook(() => useBucketTree('proj_1'))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.itemBucketMap).toEqual({
      issue_aaa: [{ name: 'Critical Fixes', description: 'Urgent production issues', rank: 1, bucket_id: 'bucket_1' }],
      issue_bbb: [{ name: 'Critical Fixes', description: 'Urgent production issues', rank: 1, bucket_id: 'bucket_1' }],
      issue_ccc: [{ name: 'Feature Work', description: 'New features', rank: 2, bucket_id: 'bucket_2' }],
    })
  })

  it('handles API errors gracefully', async () => {
    getBucketTree.mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => useBucketTree('proj_1'))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.error).toBe('Network error')
    expect(result.current.bucketTree).toBeNull()
  })

  it('provides refresh function', async () => {
    const { result } = renderHook(() => useBucketTree('proj_1', { pollInterval: 0 }))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(getBucketTree).toHaveBeenCalledTimes(1)

    await act(async () => {
      result.current.refresh()
    })

    await waitFor(() => expect(getBucketTree).toHaveBeenCalledTimes(2))
  })
})
