import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import WorkUnitCard from './WorkUnitCard'
import './WorkUnitList.css'

/**
 * Renders the list of work units produced by decomposition.
 * Shown alongside the AI chat in the decomposition page.
 * Includes independence audit summary at the top.
 */
export default function WorkUnitList({ units = [], onSelectUnit }) {
  if (units.length === 0) return null

  const overlaps = units.filter(u => u.independence?.shares_files_with?.length > 0)
  const totalDeps = units.reduce((sum, u) => sum + (u.independence?.depends_on?.length || 0), 0)

  return (
    <div className="wul">
      {/* Independence audit summary */}
      <div className="wul-audit">
        <span className="wul-audit-label">Independence Audit</span>
        <div className="wul-audit-items">
          <span className={`wul-audit-item ${overlaps.length > 0 ? 'wul-audit--warning' : 'wul-audit--ok'}`}>
            {overlaps.length > 0 ? <AlertTriangle size={12} /> : <CheckCircle2 size={12} />}
            {overlaps.length} overlap{overlaps.length !== 1 ? 's' : ''}
          </span>
          <span className="wul-audit-item wul-audit--info">
            {units.length} units
          </span>
          <span className="wul-audit-item wul-audit--info">
            {totalDeps} dependencies
          </span>
        </div>
      </div>

      {/* Work unit cards */}
      <div className="wul-list">
        {units.map((unit) => (
          <WorkUnitCard
            key={unit.id}
            unit={unit}
            allUnits={units}
            onSelect={onSelectUnit}
          />
        ))}
      </div>
    </div>
  )
}
