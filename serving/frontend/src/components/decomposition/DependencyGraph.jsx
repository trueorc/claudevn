import { GitBranch, Zap, ArrowRight } from 'lucide-react'
import './DependencyGraph.css'

/**
 * Dependency chain visualization.
 *
 * Shows the DAG as chains (linear sequences of dependent units),
 * highlights the critical path, and identifies parallel groups.
 * Falls back to layer-based view when no chain data is available.
 */
export default function DependencyGraph({ units = [], chainAnalysis = null }) {
  if (units.length === 0) return null

  const unitMap = {}
  units.forEach(u => { unitMap[u.id] = u })

  // If we have chain analysis data, show chain view
  if (chainAnalysis && chainAnalysis.chains?.length > 0) {
    return <ChainView chainAnalysis={chainAnalysis} unitMap={unitMap} units={units} />
  }

  // Fallback: layer-based view
  return <LayerView units={units} unitMap={unitMap} />
}

function ChainView({ chainAnalysis, unitMap, units }) {
  const { chains, parallel_groups: parallelGroups, critical_path_id: criticalPathId, max_depth: maxDepth } = chainAnalysis
  const parallelSet = new Set()
  const parallelGroupMap = {}
  ;(parallelGroups || []).forEach((group, gi) => {
    group.forEach(cid => {
      parallelSet.add(cid)
      parallelGroupMap[cid] = gi
    })
  })

  return (
    <div className="dg-container">
      <div className="dg-header">
        <GitBranch size={14} />
        <span className="dg-title">Dependency Chains</span>
        <span className="dg-meta">
          {chains.length} chain{chains.length !== 1 ? 's' : ''}, depth {maxDepth}
          {parallelGroups?.length > 0 && ` — ${parallelGroups.length} parallel group${parallelGroups.length !== 1 ? 's' : ''}`}
        </span>
      </div>

      {/* Parallel groups summary */}
      {parallelGroups?.length > 0 && (
        <div className="dg-parallel-summary">
          <Zap size={12} />
          <span>
            Parallel execution: {parallelGroups.map((group, i) => (
              <span key={i} className="dg-parallel-group-label">
                {i > 0 && ' | '}
                {group.join(' ∥ ')}
              </span>
            ))}
          </span>
        </div>
      )}

      {/* Chain list */}
      <div className="dg-chains">
        {chains.map(chain => {
          const isCritical = chain.chain_id === criticalPathId
          const isParallel = parallelSet.has(chain.chain_id)
          const groupIdx = parallelGroupMap[chain.chain_id]

          return (
            <div
              key={chain.chain_id}
              className={`dg-chain ${isCritical ? 'dg-chain--critical' : ''} ${isParallel ? 'dg-chain--parallel' : ''}`}
            >
              <div className="dg-chain-header">
                <span className="dg-chain-id">{chain.chain_id}</span>
                {isCritical && <span className="dg-chain-badge dg-badge--critical">Critical Path</span>}
                {isParallel && <span className="dg-chain-badge dg-badge--parallel">Parallel</span>}
                <span className="dg-chain-length">{chain.length} unit{chain.length !== 1 ? 's' : ''}</span>
              </div>
              <div className="dg-chain-units">
                {chain.unit_ids.map((uid, i) => {
                  const unit = unitMap[uid]
                  return (
                    <div key={uid} className="dg-chain-unit-wrapper">
                      {i > 0 && <ArrowRight size={12} className="dg-chain-arrow" />}
                      <div className={`dg-node dg-node--chain ${isCritical ? 'dg-node--critical-path' : ''}`}>
                        <span className={`dg-node-dot dg-node--${unit?.status || 'draft'}`} />
                        <span className="dg-node-id">{uid}</span>
                        <span className="dg-node-desc">
                          {unit?.description?.slice(0, 40) || ''}
                        </span>
                        {unit?.estimated_complexity && (
                          <span className={`dg-node-complexity dg-node-complexity--${unit.estimated_complexity}`}>
                            {unit.estimated_complexity.toUpperCase()}
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function LayerView({ units, unitMap }) {
  // Original layer-based fallback
  const depMap = {}
  units.forEach(u => {
    depMap[u.id] = u.independence?.depends_on || []
  })

  const levels = {}
  const visited = new Set()

  function computeLevel(id) {
    if (levels[id] !== undefined) return levels[id]
    if (visited.has(id)) return 0
    visited.add(id)
    const deps = depMap[id] || []
    if (deps.length === 0) { levels[id] = 0; return 0 }
    levels[id] = 1 + Math.max(...deps.map(d => depMap[d] !== undefined ? computeLevel(d) : 0))
    return levels[id]
  }

  units.forEach(u => computeLevel(u.id))

  const maxLevel = Math.max(0, ...Object.values(levels))
  const layerGroups = []
  for (let i = 0; i <= maxLevel; i++) {
    const layer = units.filter(u => levels[u.id] === i)
    if (layer.length > 0) layerGroups.push({ level: i, units: layer })
  }

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
