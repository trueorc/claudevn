import { useState, useEffect, useMemo, useCallback } from 'react'
import { FolderOpen, Filter, ChevronDown, ChevronUp, RotateCcw, SkipForward, RefreshCw } from 'lucide-react'
import EmptyState from '../components/common/EmptyState'
import { PageSubtitle } from '../components/common/InlineHint'
import { useProjectContext } from '../contexts/ProjectContext'
import { getProjectPlan, retryUnit, skipUnit } from '../api/workUnits'
import './WorkUnitsPage.css'

const STATUS_ORDER = {
  executing: 0, submitted: 1, merging: 1, waiting_compute: 2, queued: 2,
  ready: 3, failed: 4, merge_conflict: 4,
  completed: 5, verified: 5, superseded: 6, cancelled: 7, draft: 8,
}

const STATUS_COLORS = {
  executing: '#06b6d4', submitted: '#8b5cf6', merging: '#a855f7',
  waiting_compute: '#3b82f6', queued: '#3b82f6', ready: 'var(--text-muted)',
  completed: 'var(--status-online)', verified: 'var(--status-online)',
  failed: 'var(--error)', merge_conflict: '#f59e0b',
  superseded: 'var(--text-muted)', cancelled: 'var(--text-muted)',
}

const COMPLEXITY_LABELS = { xs: 'XS', s: 'S', m: 'M', l: 'L', xl: 'XL' }

function WorkUnitsPage() {
  const { activeProject } = useProjectContext()
  const projectId = activeProject?.project_id || null

  const [units, setUnits] = useState([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState('active') // active | all | completed | failed
  const [expandedId, setExpandedId] = useState(null)
  const [acting, setActing] = useState(null)

  const loadUnits = useCallback(async () => {
    if (!projectId) { setUnits([]); return }
    setLoading(true)
    try {
      const data = await getProjectPlan(projectId)
      setUnits([...(data?.active || []), ...(data?.superseded || [])])
    } catch { setUnits([]) }
    finally { setLoading(false) }
  }, [projectId])

  useEffect(() => { loadUnits() }, [loadUnits])

  const filtered = useMemo(() => {
    let list = units
    if (statusFilter === 'active') {
      list = list.filter(u => !['completed', 'verified', 'superseded', 'cancelled'].includes(u.status))
    } else if (statusFilter === 'completed') {
      list = list.filter(u => ['completed', 'verified'].includes(u.status))
    } else if (statusFilter === 'failed') {
      list = list.filter(u => ['failed', 'merge_conflict'].includes(u.status))
    }
    return list.sort((a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9))
  }, [units, statusFilter])

  // Stats
  const stats = useMemo(() => {
    const s = { total: units.length, active: 0, completed: 0, failed: 0, queued: 0 }
    units.forEach(u => {
      if (['executing', 'submitted', 'merging'].includes(u.status)) s.active++
      else if (['completed', 'verified'].includes(u.status)) s.completed++
      else if (['failed', 'merge_conflict'].includes(u.status)) s.failed++
      else if (['queued', 'waiting_compute', 'ready'].includes(u.status)) s.queued++
    })
    return s
  }, [units])

  async function handleAction(action, unitId) {
    setActing(`${action}-${unitId}`)
    try {
      if (action === 'retry') await retryUnit(unitId)
      else if (action === 'skip') await skipUnit(unitId)
      await loadUnits()
    } catch (e) { /* ignore */ }
    finally { setActing(null) }
  }

  if (!projectId) {
    return (
      <div className="wu-page">
        <header className="wu-header">
          <h1>Work Units</h1>
          <PageSubtitle>Select a project to view work units</PageSubtitle>
        </header>
        <EmptyState icon={FolderOpen} title="Select a Project" description="Select a project from the sidebar." />
      </div>
    )
  }

  return (
    <div className="wu-page">
      <header className="wu-header">
        <div className="wu-header-content">
          <h1>Work Units</h1>
          <PageSubtitle>
            {activeProject?.name} — {stats.total} units, {stats.completed} done, {stats.active} active
          </PageSubtitle>
        </div>
        <button className="wu-refresh" onClick={loadUnits} disabled={loading} title="Refresh">
          <RefreshCw size={14} className={loading ? 'wu-spin' : ''} />
        </button>
      </header>

      {/* Filter tabs */}
      <div className="wu-filters">
        {['active', 'all', 'completed', 'failed'].map(f => (
          <button
            key={f}
            className={`wu-filter-tab ${statusFilter === f ? 'wu-filter-tab--active' : ''}`}
            onClick={() => setStatusFilter(f)}
          >
            {f === 'active' ? `Active (${stats.active + stats.queued})` :
             f === 'completed' ? `Done (${stats.completed})` :
             f === 'failed' ? `Failed (${stats.failed})` :
             `All (${stats.total})`}
          </button>
        ))}
      </div>

      {/* Unit list */}
      <div className="wu-list">
        {filtered.length === 0 && !loading && (
          <div className="wu-empty">No work units match this filter.</div>
        )}
        {filtered.map(u => {
          const isExpanded = expandedId === u.id
          const isFailed = u.status === 'failed' || u.status === 'merge_conflict'
          const deps = u.independence?.depends_on || []
          const files = u.formal_spec?.target_files || []
          const criteria = u.acceptance_criteria || []
          const complexity = u.estimated_complexity

          return (
            <div key={u.id} className={`wu-item wu-item--${u.status}`}>
              <div className="wu-item-row" onClick={() => setExpandedId(isExpanded ? null : u.id)}>
                <span className="wu-status-dot" style={{ background: STATUS_COLORS[u.status] || 'var(--text-muted)' }} />
                <span className="wu-item-desc">{u.description}</span>
                {complexity && <span className="wu-complexity">{COMPLEXITY_LABELS[complexity] || complexity}</span>}
                <span className={`wu-status-badge wu-status-badge--${u.status}`}>{u.status}</span>
                {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              </div>

              {isExpanded && (
                <div className="wu-item-detail">
                  <div className="wu-detail-row">
                    <span className="wu-detail-label">ID</span>
                    <span className="wu-detail-value wu-mono">{u.id}</span>
                  </div>
                  {u.source_directive_id && (
                    <div className="wu-detail-row">
                      <span className="wu-detail-label">Directive</span>
                      <span className="wu-detail-value wu-mono">{u.source_directive_id || u.goal_ref}</span>
                    </div>
                  )}
                  {files.length > 0 && (
                    <div className="wu-detail-row">
                      <span className="wu-detail-label">Files</span>
                      <span className="wu-detail-value">{files.map(f => <code key={f} className="wu-file">{f}</code>)}</span>
                    </div>
                  )}
                  {criteria.length > 0 && (
                    <div className="wu-detail-section">
                      <span className="wu-detail-label">Criteria</span>
                      <ul className="wu-criteria">
                        {criteria.map((c, i) => <li key={i}>{c}</li>)}
                      </ul>
                    </div>
                  )}
                  {deps.length > 0 && (
                    <div className="wu-detail-row">
                      <span className="wu-detail-label">Depends on</span>
                      <span className="wu-detail-value">{deps.map(d => <code key={d} className="wu-dep">{d.slice(-8)}</code>)}</span>
                    </div>
                  )}
                  {u.assigned_instance && (
                    <div className="wu-detail-row">
                      <span className="wu-detail-label">Compute</span>
                      <span className="wu-detail-value wu-mono">{u.assigned_instance}</span>
                    </div>
                  )}
                  {isFailed && (
                    <div className="wu-item-actions">
                      <button className="wu-action wu-action--retry" onClick={() => handleAction('retry', u.id)} disabled={acting !== null}>
                        <RotateCcw size={10} /> {acting === `retry-${u.id}` ? 'Retrying...' : 'Retry'}
                      </button>
                      <button className="wu-action wu-action--skip" onClick={() => handleAction('skip', u.id)} disabled={acting !== null}>
                        <SkipForward size={10} /> {acting === `skip-${u.id}` ? 'Skipping...' : 'Skip'}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default WorkUnitsPage
