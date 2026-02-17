import { Zap } from 'lucide-react'
import './Plan.css'

function CharacterizationBanner({ statusMap, loading }) {
  if (loading || !statusMap) return null

  const entries = Object.values(statusMap)
  if (entries.length === 0) return null

  const completed = entries.filter(e => e.status === 'completed' || e.status === 'done').length
  const pending = entries.filter(e => e.status === 'pending').length
  const inProgress = entries.filter(e => e.status === 'in_progress').length
  const total = entries.length

  // Only show banner when characterization is actively in progress
  const isActive = pending > 0 || inProgress > 0
  if (!isActive) return null

  const pct = total > 0 ? Math.round((completed / total) * 100) : 0

  return (
    <div className="plan-char-banner">
      <div className="plan-char-banner-header">
        <Zap size={14} />
        <span className="plan-char-banner-title">Characterizing issues</span>
        <span className="plan-char-banner-count">{completed} of {total} complete</span>
      </div>
      <div className="plan-char-banner-bar">
        <div className="plan-char-banner-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default CharacterizationBanner
