import { useState } from 'react'
import { ChevronDown, ChevronRight, FileCode, GitBranch, AlertTriangle, CheckCircle2, Shield, ArrowUpRight, ArrowDownLeft, Target, Gauge } from 'lucide-react'
import { ScoreBadge } from './ConfidencePanel'
import ProvenanceBadge from './ProvenanceBadge'
import './WorkUnitCard.css'

const STATUS_CONFIG = {
  draft: { label: 'Draft', className: 'wuc-status--draft' },
  ready: { label: 'Ready', className: 'wuc-status--ready' },
  queued: { label: 'Queued', className: 'wuc-status--queued' },
  executing: { label: 'Executing', className: 'wuc-status--executing' },
  submitted: { label: 'Submitted', className: 'wuc-status--submitted' },
  verified: { label: 'Verified', className: 'wuc-status--verified' },
  completed: { label: 'Completed', className: 'wuc-status--completed' },
  failed_verification: { label: 'Failed', className: 'wuc-status--failed' },
}

export default function WorkUnitCard({ unit, allUnits = [], unitScores = {}, goals = [], onSelect }) {
  const [expanded, setExpanded] = useState(false)
  const statusInfo = STATUS_CONFIG[unit.status] || { label: unit.status, className: 'wuc-status--draft' }
  const hasOverlap = unit.independence?.shares_files_with?.length > 0
  const hasDeps = unit.independence?.depends_on?.length > 0
  const isSuperseded = unit.status === 'superseded'
  const supersedes = unit.supersedes?.length > 0

  return (
    <div className={`wuc ${hasOverlap ? 'wuc--overlap-warning' : ''} ${isSuperseded ? 'wuc--superseded' : ''}`} onClick={() => onSelect?.(unit)}>
      <button className="wuc-header" onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span className="wuc-id">{unit.id}</span>
        <span className={`wuc-desc ${isSuperseded ? 'wuc-desc--superseded' : ''}`}>{unit.description}</span>
        {unit.estimated_complexity && (
          <span className={`wuc-complexity wuc-complexity--${unit.estimated_complexity}`}>
            {unit.estimated_complexity.toUpperCase()}
          </span>
        )}
        {unit.source_directive_id && (
          <ProvenanceBadge
            directiveId={unit.source_directive_id}
            directiveTitle={goals.find(g => g.goal_id === unit.source_directive_id)?.title?.slice(0, 20)}
            directiveIndex={goals.findIndex(g => g.goal_id === unit.source_directive_id)}
          />
        )}
        {supersedes && <span className="wuc-supersedes-badge">Replaces {unit.supersedes.length}</span>}
        <ScoreBadge score={unitScores[unit.id]} />
        <span className={`wuc-status ${statusInfo.className}`}>{statusInfo.label}</span>
      </button>

      {/* Independence warning */}
      {hasOverlap && (
        <div className="wuc-warning">
          <AlertTriangle size={12} />
          <span>Shares files with: {unit.independence.shares_files_with.join(', ')}</span>
        </div>
      )}

      {expanded && (
        <div className="wuc-body">
          {/* Target files */}
          <div className="wuc-section">
            <span className="wuc-section-label"><FileCode size={12} /> Target Files</span>
            <div className="wuc-file-list">
              {unit.formal_spec?.target_files?.map((f, i) => (
                <span key={i} className="wuc-file">{f}</span>
              ))}
            </div>
          </div>

          {/* Dependencies */}
          {hasDeps && (
            <div className="wuc-section">
              <span className="wuc-section-label"><GitBranch size={12} /> Depends On</span>
              <div className="wuc-dep-list">
                {unit.independence.depends_on.map((depId, i) => {
                  const dep = allUnits.find(u => u.id === depId)
                  return (
                    <span key={i} className="wuc-dep">
                      {depId}
                      {dep && <span className="wuc-dep-desc"> — {dep.description?.slice(0, 30)}</span>}
                    </span>
                  )
                })}
              </div>
            </div>
          )}

          {/* Verification criteria */}
          {unit.verification_criteria?.automated?.length > 0 && (
            <div className="wuc-section">
              <span className="wuc-section-label"><Shield size={12} /> Verification</span>
              <div className="wuc-check-list">
                {unit.verification_criteria.automated.map((check, i) => (
                  <span key={i} className="wuc-check">
                    <CheckCircle2 size={10} /> {check.type}: {check.target}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Interface: Produces */}
          {unit.interface_produces?.length > 0 && (
            <div className="wuc-section">
              <span className="wuc-section-label"><ArrowUpRight size={12} /> Produces</span>
              <div className="wuc-interface-list">
                {unit.interface_produces.map((p, i) => (
                  <div key={i} className="wuc-interface-item wuc-interface--produces">
                    <span className="wuc-interface-type">{p.type}</span>
                    <span className="wuc-interface-def">{p.definition}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Interface: Consumes */}
          {unit.interface_consumes?.length > 0 && (
            <div className="wuc-section">
              <span className="wuc-section-label"><ArrowDownLeft size={12} /> Consumes</span>
              <div className="wuc-interface-list">
                {unit.interface_consumes.map((c, i) => (
                  <div key={i} className="wuc-interface-item wuc-interface--consumes">
                    <span className="wuc-interface-type">{c.type}</span>
                    <span className="wuc-interface-def">{c.definition}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Acceptance Criteria */}
          {unit.acceptance_criteria?.length > 0 && (
            <div className="wuc-section">
              <span className="wuc-section-label"><Target size={12} /> Acceptance Criteria</span>
              <div className="wuc-criteria-list">
                {unit.acceptance_criteria.map((criterion, i) => (
                  <div key={i} className="wuc-criterion">
                    <CheckCircle2 size={10} />
                    <span>{criterion}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      )}
    </div>
  )
}
