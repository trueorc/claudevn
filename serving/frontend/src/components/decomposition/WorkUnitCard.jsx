import { useState } from 'react'
import { ChevronDown, ChevronRight, FileCode, GitBranch, AlertTriangle, CheckCircle2, Shield } from 'lucide-react'
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

export default function WorkUnitCard({ unit, allUnits = [], onSelect }) {
  const [expanded, setExpanded] = useState(false)
  const statusInfo = STATUS_CONFIG[unit.status] || STATUS_CONFIG.draft
  const hasOverlap = unit.independence?.shares_files_with?.length > 0
  const hasDeps = unit.independence?.depends_on?.length > 0

  return (
    <div className={`wuc ${hasOverlap ? 'wuc--overlap-warning' : ''}`} onClick={() => onSelect?.(unit)}>
      <button className="wuc-header" onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span className="wuc-id">{unit.id}</span>
        <span className="wuc-desc">{unit.description}</span>
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

          {/* Interface contracts */}
          {unit.formal_spec?.interface_contracts?.length > 0 && (
            <div className="wuc-section">
              <span className="wuc-section-label">Interface Contracts</span>
              {unit.formal_spec.interface_contracts.map((c, i) => (
                <div key={i} className="wuc-contract">
                  <span className="wuc-contract-file">{c.file}</span>
                  <span className="wuc-contract-type">{c.type}</span>
                  <span className="wuc-contract-def">{c.definition}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
