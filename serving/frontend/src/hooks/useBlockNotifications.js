import { useMemo, useCallback, useRef, useEffect, useState } from 'react'

const STORAGE_KEY = 'claudevn_block_notifications'

function loadAcknowledged() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function saveAcknowledged(data) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch {
    // localStorage unavailable
  }
}

/**
 * Derives notification conditions for each observable block and tracks
 * acknowledgment state via localStorage.
 *
 * Returns { notifications, acknowledge } where notifications has boolean
 * flags for each block, and acknowledge(blockName) clears a block's dot.
 */
function useBlockNotifications({ health, overallStatus, planData, stats, aggregates }) {
  const ackedRef = useRef(loadAcknowledged())
  const [ackedVersion, setAckedVersion] = useState(0)

  // Reload from localStorage on mount (covers multi-tab)
  useEffect(() => {
    ackedRef.current = loadAcknowledged()
  }, [])

  // --- Derive current notable conditions ---

  // Network: any compute node unhealthy or offline
  const networkUnhealthyCount = useMemo(() => {
    const byStatus = health?.compute_registry?.by_status ?? {}
    return (byStatus.offline ?? 0) + (byStatus.degraded ?? 0)
  }, [health])

  // Backlog: blocked count
  const backlogBlockedCount = useMemo(() => {
    return stats?.blocked_count ?? stats?.by_status?.blocked ?? 0
  }, [stats])

  // Execution: blocked count + active preset
  const execBlocked = planData?.blocked_count ?? 0
  const execPreset = planData?.active_preset ?? null

  // Timing: p95 vs avg ratio — flag when p95 > 2x avg
  const timingAlert = useMemo(() => {
    const wallTime = aggregates?.find?.((a) => a.phase === 'total_wall_time')
    if (!wallTime?.avg_ms || !wallTime?.p95_ms) return false
    return wallTime.p95_ms > wallTime.avg_ms * 2
  }, [aggregates])

  const notifications = useMemo(() => {
    const acked = ackedRef.current

    // Network: red dot if unhealthy nodes exist AND count exceeds acknowledged
    const network = networkUnhealthyCount > 0 && networkUnhealthyCount > (acked.network_unhealthy ?? 0)

    // Backlog: amber dot if blocked count increased since last ack
    const backlog = backlogBlockedCount > 0 && backlogBlockedCount > (acked.backlog_blocked ?? 0)

    // Execution: dot if blocked items appeared or preset changed
    const execBlockedNew = execBlocked > 0 && execBlocked > (acked.exec_blocked ?? 0)
    const execPresetChanged = execPreset != null && execPreset !== (acked.exec_preset ?? null)
    const execution = execBlockedNew || execPresetChanged

    // Timing: dot when p95/avg ratio is alarming
    const timing = timingAlert && !acked.timing_acked

    return { network, backlog, execution, timing }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [networkUnhealthyCount, backlogBlockedCount, execBlocked, execPreset, timingAlert, ackedVersion])

  const acknowledge = useCallback((block) => {
    const acked = { ...ackedRef.current }

    switch (block) {
      case 'network':
        acked.network_unhealthy = networkUnhealthyCount
        break
      case 'backlog':
        acked.backlog_blocked = backlogBlockedCount
        break
      case 'execution':
        acked.exec_blocked = execBlocked
        acked.exec_preset = execPreset
        break
      case 'timing':
        acked.timing_acked = timingAlert
        break
      default:
        return
    }

    ackedRef.current = acked
    saveAcknowledged(acked)
    setAckedVersion((v) => v + 1)
  }, [networkUnhealthyCount, backlogBlockedCount, execBlocked, execPreset, timingAlert])

  return { notifications, acknowledge }
}

export default useBlockNotifications
