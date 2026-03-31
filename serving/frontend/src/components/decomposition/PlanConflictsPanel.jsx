import { useState } from 'react'
import { AlertTriangle, FileCode, ChevronDown, ChevronRight } from 'lucide-react'
import './PlanConflictsPanel.css'

/**
 * Shows unresolved conflicts in the project plan.
 * Each conflict has resolution options: supersede, keep both, merge.
 */
export default function PlanConflictsPanel({ conflicts = [], allUnits = [], onResolve, resolving }) {
  if (!conflicts || conflicts.length === 0) return null

  const unitMap = {}
  allUnits.forEach(u => { unitMap[u.id] = u })

  return (
    <div className="pcp">
      <div className="pcp-header">
        <AlertTriangle size={14} />
        <span className="pcp-title">Plan Conflicts</span>
        <span className="pcp-count">{conflicts.length}</span>
      </div>
      <div className="pcp-list">
        {conflicts.map((conflict) => (
          <ConflictCard
            key={conflict.conflict_id}
            conflict={conflict}
            unitMap={unitMap}
            onResolve={onResolve}
            resolving={resolving}
          />
        ))}
      </div>
    </div>
  )
}

function ConflictCard({ conflict, unitMap, onResolve, resolving }) {
  const [expanded, setExpanded] = useState(false)
  const units = (conflict.unit_ids || []).map(id => unitMap[id]).filter(Boolean)

  return (
    <div className={`pcp-card pcp-card--${conflict.severity || 'medium'}`}>
      <button className="pcp-card-header" onClick={() => setExpanded(!expanded)}>
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <span className={`pcp-severity pcp-severity--${conflict.severity}`}>
          {conflict.severity?.toUpperCase()}
        </span>
        <span className="pcp-card-desc">{conflict.description}</span>
      </button>

      {expanded && (
        <div className="pcp-card-body">
          {/* Show conflicting units */}
          <div className="pcp-units">
            {units.map((u) => (
              <div key={u.id} className="pcp-unit">
                <span className="pcp-unit-id">{u.id}</span>
                <span className="pcp-unit-desc">{u.description?.slice(0, 60)}</span>
                <span className="pcp-unit-status">{u.status}</span>
                <div className="pcp-unit-files">
                  <FileCode size={10} />
                  {(u.formal_spec?.target_files || []).slice(0, 3).map((f, i) => (
                    <span key={i} className="pcp-file">{f}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {conflict.resolution_hint && (
            <p className="pcp-hint">{conflict.resolution_hint}</p>
          )}

          {/* Resolution actions */}
          <div className="pcp-actions">
            {units.map((u) => (
              <button
                key={u.id}
                className="pcp-action pcp-action--supersede"
                onClick={() => onResolve?.(conflict.conflict_id, 'supersede', u.id)}
                disabled={resolving}
              >
                Supersede {u.id.slice(-6)}
              </button>
            ))}
            <button
              className="pcp-action pcp-action--keep"
              onClick={() => onResolve?.(conflict.conflict_id, 'keep_both')}
              disabled={resolving}
            >
              Keep Both
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
