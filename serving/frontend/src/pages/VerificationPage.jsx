import { useState, useEffect, useCallback } from 'react'
import { FolderOpen, ShieldCheck, CheckCircle2, XCircle, Clock, AlertTriangle, ChevronDown, ChevronRight, RotateCcw, ThumbsUp, Eye } from 'lucide-react'
import { useProjectContext } from '../contexts/ProjectContext'
import { getVerificationResults, getIntegrationReport, retryVerification, approveUnit } from '../api/workUnits'
import useEventStream from '../hooks/useEventStream'
import EmptyState from '../components/common/EmptyState'
import { PageSubtitle } from '../components/common/InlineHint'
import './VerificationPage.css'

const STATUS_ICONS = {
  passed: CheckCircle2,
  failed: XCircle,
  pending: Clock,
  running: Clock,
  needs_human_review: AlertTriangle,
}

const STATUS_LABELS = {
  passed: 'Passed',
  failed: 'Failed',
  pending: 'Pending',
  running: 'Running',
  needs_human_review: 'Needs Review',
}

function CheckResult({ check }) {
  const [expanded, setExpanded] = useState(false)
  const Icon = STATUS_ICONS[check.status] || Clock

  return (
    <div className={`vpage-check vpage-check--${check.status}`}>
      <button className="vpage-check-header" onClick={() => setExpanded(!expanded)}>
        <Icon size={14} />
        <span className="vpage-check-type">{check.check_type}</span>
        <span className={`vpage-check-status vpage-check-status--${check.status}`}>
          {STATUS_LABELS[check.status] || check.status}
        </span>
        {check.output && (
          expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
        )}
      </button>
      {expanded && check.output && (
        <pre className="vpage-check-output">{check.output}</pre>
      )}
      {check.details && (
        <p className="vpage-check-details">{check.details}</p>
      )}
    </div>
  )
}

function UnitCard({ unit, onRetry, onApprove }) {
  const [expanded, setExpanded] = useState(false)
  const allPassed = unit.results?.every(r => r.status === 'passed')
  const hasFailed = unit.results?.some(r => r.status === 'failed')
  const needsReview = unit.results?.some(r => r.status === 'needs_human_review')

  const overallStatus = allPassed ? 'passed' : hasFailed ? 'failed' : needsReview ? 'needs_human_review' : 'pending'
  const OverallIcon = STATUS_ICONS[overallStatus]

  return (
    <div className={`vpage-unit vpage-unit--${overallStatus}`}>
      <button className="vpage-unit-header" onClick={() => setExpanded(!expanded)}>
        <OverallIcon size={16} />
        <span className="vpage-unit-id">{unit.work_unit_id}</span>
        <span className="vpage-unit-desc">{unit.description?.slice(0, 60)}</span>
        <span className={`vpage-unit-status vpage-unit-status--${overallStatus}`}>
          {STATUS_LABELS[overallStatus]}
        </span>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>

      {expanded && (
        <div className="vpage-unit-body">
          {/* Per-check results */}
          <div className="vpage-checks">
            {(unit.results || []).map((check, i) => (
              <CheckResult key={i} check={check} />
            ))}
          </div>

          {/* Scope info */}
          {unit.target_files && (
            <div className="vpage-unit-scope">
              <span className="vpage-scope-label">Target files:</span>
              {unit.target_files.map((f, i) => (
                <span key={i} className="vpage-scope-file">{f}</span>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="vpage-unit-actions">
            {hasFailed && (
              <button className="vpage-action-btn vpage-action--retry" onClick={() => onRetry(unit.work_unit_id)}>
                <RotateCcw size={12} /> Retry
              </button>
            )}
            {needsReview && (
              <button className="vpage-action-btn vpage-action--approve" onClick={() => onApprove(unit.work_unit_id)}>
                <ThumbsUp size={12} /> Approve
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function IntegrationSection({ report }) {
  if (!report) return null

  return (
    <div className="vpage-integration">
      <h3 className="vpage-section-title">Cross-Unit Integration</h3>
      <div className="vpage-integration-summary">
        <span>Pairs checked: {report.unit_pairs_checked || 0}</span>
        <span>Merge conflicts: {report.merge_conflicts?.length || 0}</span>
        <span>Interface mismatches: {report.interface_mismatches?.length || 0}</span>
      </div>

      {report.merge_conflicts?.length > 0 && (
        <div className="vpage-conflicts">
          <h4>Merge Conflicts</h4>
          {report.merge_conflicts.map((c, i) => (
            <div key={i} className="vpage-conflict-item">
              <XCircle size={12} />
              <span>{c.unit_a} + {c.unit_b}: {c.details}</span>
            </div>
          ))}
        </div>
      )}

      {report.interface_mismatches?.length > 0 && (
        <div className="vpage-conflicts">
          <h4>Interface Mismatches</h4>
          {report.interface_mismatches.map((m, i) => (
            <div key={i} className="vpage-conflict-item">
              <AlertTriangle size={12} />
              <span>{m.unit_a} + {m.unit_b}: {m.details}</span>
            </div>
          ))}
        </div>
      )}

      {(report.merge_conflicts?.length === 0 && report.interface_mismatches?.length === 0) && (
        <p className="vpage-integration-clear">
          <CheckCircle2 size={14} /> All units integrate cleanly
        </p>
      )}
    </div>
  )
}

export default function VerificationPage() {
  const { activeProject } = useProjectContext()
  const projectId = activeProject?.project_id || null

  const [results, setResults] = useState([])
  const [integration, setIntegration] = useState(null)
  const [loading, setLoading] = useState(true)

  // Subscribe to verification events
  useEventStream({
    patterns: ['verification.*'],
    enabled: !!projectId,
    onEvent: useCallback(() => {
      // Refresh on any verification event
      if (projectId) loadResults()
    }, [projectId]), // eslint-disable-line react-hooks/exhaustive-deps
  })

  const loadResults = useCallback(async () => {
    if (!projectId) return
    try {
      const [verResults, intReport] = await Promise.allSettled([
        getVerificationResults(projectId),
        getIntegrationReport(projectId),
      ])
      if (verResults.status === 'fulfilled') setResults(verResults.value?.results || [])
      if (intReport.status === 'fulfilled') setIntegration(intReport.value)
    } catch { /* API not wired yet */ }
    finally { setLoading(false) }
  }, [projectId])

  useEffect(() => { loadResults() }, [loadResults])

  const handleRetry = async (unitId) => {
    try {
      await retryVerification(unitId)
      await loadResults()
    } catch (err) {
      console.error('Retry failed:', err)
    }
  }

  const handleApprove = async (unitId) => {
    try {
      await approveUnit(unitId)
      await loadResults()
    } catch (err) {
      console.error('Approve failed:', err)
    }
  }

  if (!projectId) {
    return (
      <div className="vpage">
        <div className="vpage-header">
          <h1>Verification</h1>
          <PageSubtitle>Select a project to view verification results</PageSubtitle>
        </div>
        <EmptyState icon={FolderOpen} title="Select a Project" description="Select a project from the sidebar to view verification results." />
      </div>
    )
  }

  // Summary counts
  const passed = results.filter(r => r.results?.every(c => c.status === 'passed'))
  const failed = results.filter(r => r.results?.some(c => c.status === 'failed'))
  const pending = results.filter(r => r.results?.some(c => c.status === 'pending'))
  const needsReview = results.filter(r => r.results?.some(c => c.status === 'needs_human_review'))

  return (
    <div className="vpage">
      <div className="vpage-header">
        <div>
          <h1>Verification</h1>
          <PageSubtitle>
            {activeProject ? `Integration verification for ${activeProject.name}` : 'Select a project'}
          </PageSubtitle>
        </div>
      </div>

      {/* Summary bar */}
      <div className="vpage-summary">
        <div className="vpage-summary-item vpage-summary--passed">
          <CheckCircle2 size={16} />
          <span className="vpage-summary-count">{passed.length}</span>
          <span className="vpage-summary-label">Passed</span>
        </div>
        <div className="vpage-summary-item vpage-summary--failed">
          <XCircle size={16} />
          <span className="vpage-summary-count">{failed.length}</span>
          <span className="vpage-summary-label">Failed</span>
        </div>
        <div className="vpage-summary-item vpage-summary--pending">
          <Clock size={16} />
          <span className="vpage-summary-count">{pending.length}</span>
          <span className="vpage-summary-label">Pending</span>
        </div>
        <div className="vpage-summary-item vpage-summary--review">
          <AlertTriangle size={16} />
          <span className="vpage-summary-count">{needsReview.length}</span>
          <span className="vpage-summary-label">Needs Review</span>
        </div>
      </div>

      {/* Integration report */}
      <IntegrationSection report={integration} />

      {/* Per-unit results */}
      <div className="vpage-units">
        <h3 className="vpage-section-title">Per-Unit Results</h3>
        {results.length === 0 && !loading ? (
          <EmptyState icon={ShieldCheck} title="No Results Yet" description="Verification results will appear here as work units complete execution." />
        ) : (
          <div className="vpage-unit-list">
            {results.map((unit) => (
              <UnitCard key={unit.work_unit_id} unit={unit} onRetry={handleRetry} onApprove={handleApprove} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
