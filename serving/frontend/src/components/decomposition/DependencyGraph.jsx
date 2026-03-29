import { GitBranch } from 'lucide-react'
import './DependencyGraph.css'

/**
 * Simple text-based dependency visualization.
 * Shows the DAG as a list with indentation for depth levels.
 * A visual graph component (e.g., dagre/react-flow) can replace this later.
 */
export default function DependencyGraph({ units = [] }) {
  if (units.length === 0) return null

  // Build adjacency and compute layers (topological levels)
  const depMap = {}
  const dependents = {}
  units.forEach(u => {
    depMap[u.id] = u.independence?.depends_on || []
    ;(u.independence?.depends_on || []).forEach(dep => {
      if (!dependents[dep]) dependents[dep] = []
      dependents[dep].push(u.id)
    })
  })

  // Compute depth level for each unit
  const levels = {}
  const visited = new Set()

  function computeLevel(id) {
    if (levels[id] !== undefined) return levels[id]
    if (visited.has(id)) return 0 // cycle guard
    visited.add(id)
    const deps = depMap[id] || []
    if (deps.length === 0) { levels[id] = 0; return 0 }
    levels[id] = 1 + Math.max(...deps.map(d => depMap[d] !== undefined ? computeLevel(d) : 0))
    return levels[id]
  }

  units.forEach(u => computeLevel(u.id))

  // Group by level
  const maxLevel = Math.max(0, ...Object.values(levels))
  const layerGroups = []
  for (let i = 0; i <= maxLevel; i++) {
    const layer = units.filter(u => levels[u.id] === i)
    if (layer.length > 0) layerGroups.push({ level: i, units: layer })
  }

  const unitMap = {}
  units.forEach(u => { unitMap[u.id] = u })

  return (
    <div className="dg-container">
      <div className="dg-header">
        <GitBranch size={14} />
        <span className="dg-title">Dependency Graph</span>
        <span className="dg-meta">{units.length} units, depth {maxLevel}</span>
      </div>
      <div className="dg-layers">
        {layerGroups.map(({ level, units: layerUnits }) => (
          <div key={level} className="dg-layer">
            <span className="dg-layer-label">
              {level === 0 ? 'Root' : `Level ${level}`}
            </span>
            <div className="dg-layer-units">
              {layerUnits.map(u => (
                <div key={u.id} className="dg-node">
                  <span className={`dg-node-dot dg-node--${u.status || 'draft'}`} />
                  <span className="dg-node-id">{u.id}</span>
                  <span className="dg-node-desc">{u.description?.slice(0, 50)}</span>
                  {(depMap[u.id] || []).length > 0 && (
                    <span className="dg-node-deps">
                      needs: {depMap[u.id].map(d => unitMap[d]?.id || d).join(', ')}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
