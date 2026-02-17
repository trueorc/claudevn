import { useMemo, useState } from 'react'
import { Circle } from 'lucide-react'
import Spinner from '../common/Spinner'
import EmptyState from '../common/EmptyState'
import './IssueDependencyGraph.css'

const NODE_W = 144
const NODE_H = 46
const H_GAP = 72
const V_GAP = 14
const MARGIN_X = 24
const MARGIN_Y = 24

/**
 * Computes topological layers using longest-path BFS.
 * Layer 0 = no prerequisites (leftmost).
 * Layer N = max(layer of prerequisites) + 1 (rightmost).
 *
 * Edges: from = dependent, to = prerequisite
 */
function computeLayers(issueNodes, depEdges) {
  const layers = {}
  issueNodes.forEach(n => { layers[n.id] = 0 })

  // Iterate until stable (handles chains of arbitrary depth)
  for (let pass = 0; pass < issueNodes.length; pass++) {
    let changed = false
    depEdges.forEach(e => {
      if (layers[e.to] === undefined || layers[e.from] === undefined) return
      const newLayer = layers[e.to] + 1
      if (newLayer > layers[e.from]) {
        layers[e.from] = newLayer
        changed = true
      }
    })
    if (!changed) break
  }

  return layers
}

/**
 * Given nodes and per-layer groups, compute pixel positions.
 * Returns posMap: { nodeId: { ...node, x, y } } and SVG dimensions.
 */
function computePositions(issueNodes, layers, depEdges) {
  const layerGroups = {}
  issueNodes.forEach(n => {
    const l = layers[n.id] ?? 0
    if (!layerGroups[l]) layerGroups[l] = []
    layerGroups[l].push(n)
  })

  const layerKeys = Object.keys(layerGroups).map(Number).sort((a, b) => a - b)
  const maxNodesInLayer = Math.max(...Object.values(layerGroups).map(g => g.length))
  const totalHeight = maxNodesInLayer * NODE_H + Math.max(0, maxNodesInLayer - 1) * V_GAP

  const posMap = {}
  layerKeys.forEach(layer => {
    const group = layerGroups[layer]
    const x = MARGIN_X + layer * (NODE_W + H_GAP)
    const groupHeight = group.length * NODE_H + Math.max(0, group.length - 1) * V_GAP
    const startY = MARGIN_Y + (totalHeight - groupHeight) / 2

    group.forEach((node, idx) => {
      posMap[node.id] = {
        ...node,
        x,
        y: startY + idx * (NODE_H + V_GAP),
        layer,
      }
    })
  })

  const maxLayer = layerKeys.length > 0 ? Math.max(...layerKeys) : 0
  const svgWidth = MARGIN_X * 2 + (maxLayer + 1) * NODE_W + maxLayer * H_GAP
  const svgHeight = MARGIN_Y * 2 + totalHeight

  return {
    posMap,
    width: Math.max(svgWidth, 320),
    height: Math.max(svgHeight, 200),
  }
}

function getStatusColor(status) {
  switch (status?.toLowerCase()) {
    case 'done':
    case 'completed':
      return '#6b7280'
    case 'in_progress':
    case 'in_review':
      return '#3b82f6'
    case 'ready':
      return '#22c55e'
    case 'blocked':
      return '#ef4444'
    default:
      return '#71717a'
  }
}

function getStatusFill(status) {
  switch (status?.toLowerCase()) {
    case 'done':
    case 'completed':
      return 'rgba(107,114,128,0.10)'
    case 'in_progress':
    case 'in_review':
      return 'rgba(59,130,246,0.10)'
    case 'ready':
      return 'rgba(34,197,94,0.10)'
    case 'blocked':
      return 'rgba(239,68,68,0.10)'
    default:
      return 'rgba(113,113,122,0.07)'
  }
}

function truncate(str, max) {
  if (!str) return ''
  return str.length > max ? str.slice(0, max - 1) + '…' : str
}

/**
 * Cubic bezier path from the right-center of the prerequisite node
 * to the left-center of the dependent node.
 */
function makePath(prereq, dep) {
  const x1 = prereq.x + NODE_W
  const y1 = prereq.y + NODE_H / 2
  const x2 = dep.x
  const y2 = dep.y + NODE_H / 2
  const cx = (x1 + x2) / 2
  return `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`
}

/**
 * IssueDependencyGraph renders a left-to-right DAG of issues connected
 * by their depends_on relationships. Issues with no prerequisites appear
 * on the left; dependent issues cascade to the right.
 *
 * Props:
 *   graphData: { nodes: [...], edges: [...] } — same shape as WorkMapGraph
 *   loading: bool
 */
function IssueDependencyGraph({ graphData, loading }) {
  const [hoveredId, setHoveredId] = useState(null)

  const { layoutNodes, layoutEdges, posMap, width, height } = useMemo(() => {
    if (!graphData?.nodes?.length) {
      return { layoutNodes: [], layoutEdges: [], posMap: {}, width: 400, height: 300 }
    }

    const issueNodes = graphData.nodes.filter(n => n.type === 'issue')
    const depEdges = (graphData.edges || []).filter(e => e.type === 'depends_on')

    const nodeIds = new Set(issueNodes.map(n => n.id))
    const validEdges = depEdges.filter(e => nodeIds.has(e.from) && nodeIds.has(e.to))

    const layers = computeLayers(issueNodes, validEdges)
    const { posMap, width, height } = computePositions(issueNodes, layers, validEdges)

    return {
      layoutNodes: Object.values(posMap),
      layoutEdges: validEdges,
      posMap,
      width,
      height,
    }
  }, [graphData])

  // Set of node IDs reachable from the hovered node (direct neighbors only)
  const connectedIds = useMemo(() => {
    if (!hoveredId) return null
    const ids = new Set([hoveredId])
    layoutEdges.forEach(e => {
      if (e.from === hoveredId || e.to === hoveredId) {
        ids.add(e.from)
        ids.add(e.to)
      }
    })
    return ids
  }, [hoveredId, layoutEdges])

  if (loading) {
    return (
      <div className="issue-dep-graph">
        <div className="idg-loading">
          <Spinner />
        </div>
      </div>
    )
  }

  if (!layoutNodes.length) {
    return (
      <EmptyState
        icon={Circle}
        title="No issues to display"
        description="Issue dependencies will be visualized here"
      />
    )
  }

  return (
    <div className="issue-dep-graph">
      <div className="idg-scroll">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width={width}
          height={height}
          className="idg-svg"
        >
          <defs>
            <marker id="idg-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
              <polygon points="0 0, 7 3.5, 0 7" fill="var(--border-light)" />
            </marker>
            <marker id="idg-arrow-active" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
              <polygon points="0 0, 7 3.5, 0 7" fill="var(--primary)" />
            </marker>
          </defs>

          {/* Edges — rendered first so nodes appear on top */}
          {layoutEdges.map((edge, i) => {
            const prereq = posMap[edge.to]    // prerequisite (left node)
            const dep = posMap[edge.from]     // dependent (right node)
            if (!prereq || !dep) return null

            const active = hoveredId && (edge.from === hoveredId || edge.to === hoveredId)
            const dimmed = hoveredId && !active

            return (
              <path
                key={`edge-${i}`}
                d={makePath(prereq, dep)}
                className={[
                  'idg-edge',
                  active ? 'idg-edge--active' : '',
                  dimmed ? 'idg-edge--dimmed' : '',
                ].join(' ')}
                markerEnd={active ? 'url(#idg-arrow-active)' : 'url(#idg-arrow)'}
              />
            )
          })}

          {/* Nodes */}
          {layoutNodes.map(node => {
            const color = getStatusColor(node.status)
            const fill = getStatusFill(node.status)
            const hovered = hoveredId === node.id
            const dimmed = hoveredId && connectedIds && !connectedIds.has(node.id)

            return (
              <g
                key={node.id}
                className={[
                  'idg-node',
                  hovered ? 'idg-node--hovered' : '',
                  dimmed ? 'idg-node--dimmed' : '',
                ].join(' ')}
                transform={`translate(${node.x}, ${node.y})`}
                onMouseEnter={() => setHoveredId(node.id)}
                onMouseLeave={() => setHoveredId(null)}
              >
                <rect
                  width={NODE_W}
                  height={NODE_H}
                  rx="6"
                  ry="6"
                  fill={fill}
                  stroke={color}
                  strokeWidth={hovered ? 2 : 1.5}
                  className="idg-node-rect"
                />
                <text
                  x="10"
                  y="17"
                  className="idg-node-number"
                  fill={color}
                >
                  #{node.number ?? node.id?.slice(0, 8)}
                </text>
                <text
                  x="10"
                  y="34"
                  className="idg-node-title"
                >
                  {truncate(node.title, 20)}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      {/* Legend */}
      <div className="idg-legend">
        <div className="idg-legend-group">
          <span className="idg-legend-heading">Status</span>
          <div className="idg-legend-row">
            <span className="idg-legend-dot" style={{ background: '#22c55e' }} />
            Ready
          </div>
          <div className="idg-legend-row">
            <span className="idg-legend-dot" style={{ background: '#3b82f6' }} />
            In Progress
          </div>
          <div className="idg-legend-row">
            <span className="idg-legend-dot" style={{ background: '#ef4444' }} />
            Blocked
          </div>
          <div className="idg-legend-row">
            <span className="idg-legend-dot" style={{ background: '#6b7280' }} />
            Done
          </div>
          <div className="idg-legend-row">
            <span className="idg-legend-dot" style={{ background: '#71717a' }} />
            Backlog
          </div>
        </div>
        <div className="idg-legend-group">
          <span className="idg-legend-heading">Edges</span>
          <div className="idg-legend-row">
            <svg width="30" height="12" viewBox="0 0 30 12" className="idg-legend-edge-svg">
              <line x1="0" y1="6" x2="22" y2="6" stroke="var(--border-light)" strokeWidth="1.5" />
              <polygon points="22 3, 29 6, 22 9" fill="var(--border-light)" />
            </svg>
            Depends on
          </div>
        </div>
      </div>
    </div>
  )
}

export default IssueDependencyGraph
