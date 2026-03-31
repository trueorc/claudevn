import { useState } from 'react'
import { ChevronDown, ChevronRight, Layers } from 'lucide-react'
import WorkUnitCard from './WorkUnitCard'
import ProvenanceBadge from './ProvenanceBadge'
import './UnifiedWorkUnitList.css'

const GROUP_OPTIONS = [
  { key: 'directive', label: 'By Directive' },
  { key: 'status', label: 'By Status' },
  { key: 'none', label: 'Flat List' },
]

/**
 * Unified work unit list — shows ALL active units across directives.
 * Supports grouping by directive, status, or flat list.
 * Superseded units shown in collapsible section.
 */
export default function UnifiedWorkUnitList({
  activeUnits = [],
  supersededUnits = [],
  goals = [],
  unitScores = {},
  onSelectGoal,
}) {
  const [groupBy, setGroupBy] = useState('directive')
  const [showSuperseded, setShowSuperseded] = useState(false)

  if (activeUnits.length === 0 && supersededUnits.length === 0) return null

  // Build goal lookup for provenance
  const goalMap = {}
  const goalIndex = {}
  goals.forEach((g, i) => {
    goalMap[g.goal_id] = g
    goalIndex[g.goal_id] = i
  })

  // Group active units
  const groups = groupUnits(activeUnits, groupBy, goalMap)

  return (
    <div className="uwl">
      <div className="uwl-header">
        <Layers size={14} />
        <span className="uwl-title">Project Plan</span>
        <span className="uwl-count">{activeUnits.length} active</span>
        <div className="uwl-group-toggle">
          {GROUP_OPTIONS.map(opt => (
            <button
              key={opt.key}
              className={`uwl-group-btn ${groupBy === opt.key ? 'uwl-group-btn--active' : ''}`}
              onClick={() => setGroupBy(opt.key)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Grouped units */}
      <div className="uwl-groups">
        {groups.map(group => (
          <div key={group.key} className="uwl-group">
            {group.label && (
              <div className="uwl-group-label">
                {group.directiveId && (
                  <ProvenanceBadge
                    directiveId={group.directiveId}
                    directiveTitle={group.label}
                    directiveIndex={goalIndex[group.directiveId] || 0}
                  />
                )}
                {!group.directiveId && <span>{group.label}</span>}
                <span className="uwl-group-count">{group.units.length}</span>
              </div>
            )}
            <div className="uwl-cards">
              {group.units.map(unit => (
                <WorkUnitCard
                  key={unit.id}
                  unit={unit}
                  allUnits={activeUnits}
                  unitScores={unitScores}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Superseded units */}
      {supersededUnits.length > 0 && (
        <div className="uwl-superseded">
          <button
            className="uwl-superseded-toggle"
            onClick={() => setShowSuperseded(!showSuperseded)}
          >
            {showSuperseded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            <span>{supersededUnits.length} superseded unit{supersededUnits.length !== 1 ? 's' : ''}</span>
          </button>
          {showSuperseded && (
            <div className="uwl-superseded-list">
              {supersededUnits.map(unit => (
                <div key={unit.id} className="uwl-superseded-item">
                  <span className="uwl-superseded-id">{unit.id}</span>
                  <span className="uwl-superseded-desc">{unit.description?.slice(0, 60)}</span>
                  {unit.superseded_by && (
                    <span className="uwl-superseded-by">replaced by {unit.superseded_by.slice(-8)}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function groupUnits(units, groupBy, goalMap) {
  if (groupBy === 'none') {
    return [{ key: 'all', label: null, units }]
  }

  const grouped = {}
  for (const u of units) {
    let key, label, directiveId
    if (groupBy === 'directive') {
      key = u.source_directive_id || u.goal_ref || 'unknown'
      directiveId = key
      const goal = goalMap[key]
      label = goal?.title || goal?.description?.slice(0, 40) || key.slice(-8)
    } else if (groupBy === 'status') {
      key = u.status || 'draft'
      label = key.charAt(0).toUpperCase() + key.slice(1)
      directiveId = null
    }
    if (!grouped[key]) grouped[key] = { key, label, directiveId, units: [] }
    grouped[key].units.push(u)
  }

  return Object.values(grouped)
}
