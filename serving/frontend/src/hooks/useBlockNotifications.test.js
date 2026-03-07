import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, beforeEach } from 'vitest'
import useBlockNotifications from './useBlockNotifications'

describe('useBlockNotifications', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  const baseProps = {
    health: null,
    overallStatus: 'healthy',
    planData: null,
    stats: null,
    aggregates: null,
  }

  it('returns no notifications when all data is null', () => {
    const { result } = renderHook(() => useBlockNotifications(baseProps))
    expect(result.current.notifications).toEqual({
      network: false,
      backlog: false,
      execution: false,
      timing: false,
    })
  })

  it('shows network notification when compute nodes are offline', () => {
    const props = {
      ...baseProps,
      health: {
        compute_registry: {
          by_status: { online: 2, offline: 1 },
          total_instances: 3,
        },
      },
    }
    const { result } = renderHook(() => useBlockNotifications(props))
    expect(result.current.notifications.network).toBe(true)
  })

  it('shows network notification when compute nodes are degraded', () => {
    const props = {
      ...baseProps,
      health: {
        compute_registry: {
          by_status: { online: 2, degraded: 1 },
          total_instances: 3,
        },
      },
    }
    const { result } = renderHook(() => useBlockNotifications(props))
    expect(result.current.notifications.network).toBe(true)
  })

  it('does not show network notification when all nodes are online', () => {
    const props = {
      ...baseProps,
      health: {
        compute_registry: {
          by_status: { online: 3 },
          total_instances: 3,
        },
      },
    }
    const { result } = renderHook(() => useBlockNotifications(props))
    expect(result.current.notifications.network).toBe(false)
  })

  it('clears network notification after acknowledge', () => {
    const props = {
      ...baseProps,
      health: {
        compute_registry: {
          by_status: { online: 2, offline: 1 },
          total_instances: 3,
        },
      },
    }
    const { result, rerender } = renderHook(() => useBlockNotifications(props))
    expect(result.current.notifications.network).toBe(true)

    act(() => {
      result.current.acknowledge('network')
    })

    rerender()
    expect(result.current.notifications.network).toBe(false)
  })

  it('shows backlog notification when blocked count increases', () => {
    const props = {
      ...baseProps,
      stats: { blocked_count: 3, by_status: { blocked: 3 } },
    }
    const { result } = renderHook(() => useBlockNotifications(props))
    expect(result.current.notifications.backlog).toBe(true)
  })

  it('does not show backlog notification when blocked count is zero', () => {
    const props = {
      ...baseProps,
      stats: { blocked_count: 0, by_status: { blocked: 0 } },
    }
    const { result } = renderHook(() => useBlockNotifications(props))
    expect(result.current.notifications.backlog).toBe(false)
  })

  it('clears backlog notification after acknowledge', () => {
    const props = {
      ...baseProps,
      stats: { blocked_count: 2 },
    }
    const { result, rerender } = renderHook(() => useBlockNotifications(props))
    expect(result.current.notifications.backlog).toBe(true)

    act(() => {
      result.current.acknowledge('backlog')
    })

    rerender()
    expect(result.current.notifications.backlog).toBe(false)
  })

  it('shows execution notification when blocked items appear', () => {
    const props = {
      ...baseProps,
      planData: { blocked_count: 2 },
    }
    const { result } = renderHook(() => useBlockNotifications(props))
    expect(result.current.notifications.execution).toBe(true)
  })

  it('shows execution notification when preset changes', () => {
    const props = {
      ...baseProps,
      planData: { blocked_count: 0, active_preset: 'build' },
    }
    const { result } = renderHook(() => useBlockNotifications(props))
    expect(result.current.notifications.execution).toBe(true)
  })

  it('clears execution notification after acknowledge', () => {
    const props = {
      ...baseProps,
      planData: { blocked_count: 1, active_preset: 'build' },
    }
    const { result, rerender } = renderHook(() => useBlockNotifications(props))
    expect(result.current.notifications.execution).toBe(true)

    act(() => {
      result.current.acknowledge('execution')
    })

    rerender()
    expect(result.current.notifications.execution).toBe(false)
  })

  it('shows timing notification when p95 exceeds 2x avg', () => {
    const props = {
      ...baseProps,
      aggregates: [{ phase: 'total_wall_time', avg_ms: 1000, p95_ms: 3000, count: 10 }],
    }
    const { result } = renderHook(() => useBlockNotifications(props))
    expect(result.current.notifications.timing).toBe(true)
  })

  it('does not show timing notification when p95 is within 2x avg', () => {
    const props = {
      ...baseProps,
      aggregates: [{ phase: 'total_wall_time', avg_ms: 1000, p95_ms: 1500, count: 10 }],
    }
    const { result } = renderHook(() => useBlockNotifications(props))
    expect(result.current.notifications.timing).toBe(false)
  })

  it('clears timing notification after acknowledge', () => {
    const props = {
      ...baseProps,
      aggregates: [{ phase: 'total_wall_time', avg_ms: 1000, p95_ms: 3000, count: 10 }],
    }
    const { result, rerender } = renderHook(() => useBlockNotifications(props))
    expect(result.current.notifications.timing).toBe(true)

    act(() => {
      result.current.acknowledge('timing')
    })

    rerender()
    expect(result.current.notifications.timing).toBe(false)
  })

  it('persists acknowledged state in localStorage', () => {
    const props = {
      ...baseProps,
      health: {
        compute_registry: {
          by_status: { online: 2, offline: 1 },
          total_instances: 3,
        },
      },
    }
    const { result } = renderHook(() => useBlockNotifications(props))

    act(() => {
      result.current.acknowledge('network')
    })

    const stored = JSON.parse(localStorage.getItem('claudevn_block_notifications'))
    expect(stored.network_unhealthy).toBe(1)
  })

  it('re-shows notification when condition worsens after acknowledge', () => {
    // First: 1 offline, acknowledge it
    const props1 = {
      ...baseProps,
      health: {
        compute_registry: {
          by_status: { online: 2, offline: 1 },
          total_instances: 3,
        },
      },
    }
    const { result, rerender } = renderHook(
      ({ props }) => useBlockNotifications(props),
      { initialProps: { props: props1 } }
    )

    act(() => {
      result.current.acknowledge('network')
    })

    // Now: 2 offline — should re-trigger
    const props2 = {
      ...baseProps,
      health: {
        compute_registry: {
          by_status: { online: 1, offline: 2 },
          total_instances: 3,
        },
      },
    }
    rerender({ props: props2 })
    expect(result.current.notifications.network).toBe(true)
  })
})
