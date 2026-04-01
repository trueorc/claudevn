import { useState } from 'react'
import { AlertTriangle, Clock, XCircle, X, RotateCcw, SkipForward, ChevronDown, ChevronUp } from 'lucide-react'
import { retryUnit, skipUnit } from '../../api/workUnits'
import './StuckWorkDetector.css'

/**
 * Prominently surfaces work units that appear stuck or failed.
 * Each item can be dismissed, retried, or skipped.
 */
const STORAGE_KEY = 'claudevn:dismissed_attention'

function loadDismissed(projectId) {
  try {
    const raw = localStorage.getItem(`${STORAGE_KEY}:${projectId}`)
    return raw ? new Set(JSON.parse(raw)) : new Set()
  } catch { return new Set() }
}

function saveDismissed(projectId, ids) {
  try {
    localStorage.setItem(`${STORAGE_KEY}:${projectId}`, JSON.stringify([...ids]))
  } catch { /* ignore */ }
}

export default function StuckWorkDetector({ items = [], projectId, onDismiss, onAction }) {
  const [expanded, setExpanded] = useState(null)
  const [acting, setActing] = useState(null)
  const [dismissed, setDismissed] = useState(() => loadDismissed(projectId))

  const visible = items.filter(i => !dismissed.has(i.id || i.work_unit_id))
  if (visible.length === 0) return null

  const failed = visible.filter(i => i.type === 'failed')
  const stuck = visible.filter(i => i.type === 'stuck')
  const stale = visible.filter(i => i.type === 'stale')

  function dismiss(itemId) {
    setDismissed(prev => {
      const next = new Set([...prev, itemId])
      saveDismissed(projectId, next)
      return next
    })
    if (onDismiss) onDismiss(itemId)
  }

  function dismissAll() {
    const allIds = visible.map(i => i.id || i.work_unit_id)
    setDismissed(prev => {
      const next = new Set([...prev, ...allIds])
      saveDismissed(projectId, next)
      return next
    })
    if (onDismiss) onDismiss('all')
  }

  async function handleAction(action, unitId) {
    setActing(`${action}-${unitId}`)
    try {
      if (action === 'retry') await retryUnit(unitId)
      else if (action === 'skip') await skipUnit(unitId)
      dismiss(unitId)
      if (onAction) onAction(action, unitId)
    } catch (e) {
      // stay visible on error
    } finally {
      setActing(null)
    }
  }

  function toggleExpand(itemId) {
    setExpanded(prev => prev === itemId ? null : itemId)
  }

  function renderItem(item, type) {
    const itemId = item.id || item.work_unit_id
    const isExpanded = expanded === itemId
    const Icon = type === 'failed' ? XCircle : Clock
    const cssClass = `swd-item swd-item--${type}`

    return (
      <div key={itemId} className={cssClass}>
        <Icon size={14} />
        <div className="swd-item-content">
          <div className="swd-item-header" onClick={() => toggleExpand(itemId)}>
            <span className="swd-item-id">{itemId}</span>
            <span className="swd-item-label">{item.description || type}</span>
            {item.reason && !isExpanded && (
              <ChevronDown size={10} className="swd-expand-icon" />
            )}
            {isExpanded && <ChevronUp size={10} className="swd-expand-icon" />}
          </div>
          {isExpanded && item.reason && (
            <p className="swd-item-reason swd-item-reason--full">{item.reason}</p>
          )}
          {isExpanded && type === 'failed' && (
            <div className="swd-item-actions">
              <button
                className="swd-action swd-action--retry"
                onClick={() => handleAction('retry', itemId)}
                disabled={acting !== null}
              >
                <RotateCcw size={10} />
                {acting === `retry-${itemId}` ? 'Retrying...' : 'Retry'}
              </button>
              <button
                className="swd-action swd-action--skip"
                onClick={() => handleAction('skip', itemId)}
                disabled={acting !== null}
              >
                <SkipForward size={10} />
                {acting === `skip-${itemId}` ? 'Skipping...' : 'Skip'}
              </button>
            </div>
          )}
        </div>
        <button className="swd-dismiss" onClick={() => dismiss(itemId)} title="Dismiss">
          <X size={12} />
        </button>
      </div>
    )
  }

  return (
    <div className="swd-container">
      <div className="swd-header">
        <AlertTriangle size={14} className="swd-header-icon" />
        <span className="swd-title">Attention Required</span>
        <span className="swd-count">{visible.length}</span>
        {visible.length > 1 && (
          <button className="swd-clear-all" onClick={dismissAll}>Clear all</button>
        )}
      </div>

      <div className="swd-list">
        {failed.map(item => renderItem(item, 'failed'))}
        {stuck.map(item => renderItem(item, 'stuck'))}
        {stale.map(item => renderItem(item, 'stale'))}
      </div>
    </div>
  )
}
