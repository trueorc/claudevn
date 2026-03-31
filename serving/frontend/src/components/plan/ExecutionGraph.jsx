import { useMemo, useState } from 'react'
import { computeLayers, computePositions, computeSvgSize } from '../../utils/dagLayout'
import './ExecutionGraph.css'

const NODE_WIDTH = 180
const NODE_HEIGHT = 48
const LAYER_GAP = 100
const NODE_GAP = 16

const STATUS_COLORS = {
  draft: { fill: '#2a2a2a', stroke: '#555', text: '#a1a1aa' },
  ready: { fill: '#1a1a2e', stroke: '#6366f1', text: '#a5b4fc' },
  queued: { fill: '#1a1a2e', stroke: '#3b82f6', text: '#93c5fd' },
  executing: { fill: '#1a2332', stroke: '#3b82f6', text: '#93c5fd' },
  completed: { fill: '#0f2918', stroke: '#22c55e', text: '#86efac' },
  verified: { fill: '#0f2918', stroke: '#22c55e', text: '#86efac' },
  submitted: { fill: '#1a2332', stroke: '#8b5cf6', text: '#c4b5fd' },
  failed: { fill: '#2a1515', stroke: '#ef4444', text: '#fca5a5' },
  failed_verification: { fill: '#2a1515', stroke: '#ef4444', text: '#fca5a5' },
  stuck: { fill: '#2a2010', stroke: '#f59e0b', text: '#fcd34d' },
}

const DEFAULT_COLOR = { fill: '#1a1a1a', stroke: '#555', text: '#a1a1aa' }

/**
 * SVG-based execution dependency graph.
 *
 * Renders work units as nodes in a DAG, colored by execution status.
 * Critical path is highlighted. Click a node for detail.
 */
export default function ExecutionGraph({
  nodes = [],
  edges = [],
  criticalPath = [],
  selectedNodeId = null,
  onNodeClick,
}) {
  const [hoveredId, setHoveredId] = useState(null)
  const criticalSet = useMemo(() => new Set(criticalPath), [criticalPath])

  // Compute layout
  const layers = useMemo(() => computeLayers(nodes), [nodes])
  const positions = useMemo(
    () => computePositions(nodes, layers, { nodeWidth: NODE_WIDTH, nodeHeight: NODE_HEIGHT, layerGap: LAYER_GAP, nodeGap: NODE_GAP }),
    [nodes, layers]
  )
  const svgSize = useMemo(
    () => computeSvgSize(positions, { nodeWidth: NODE_WIDTH, nodeHeight: NODE_HEIGHT }),
    [positions]
  )

  if (nodes.length === 0) {
    return (
      <div className="eg-empty">
        <p>No work units in the execution plan yet.</p>
        <p className="eg-empty-hint">Approve a decomposition on the Plan page to queue work.</p>
      </div>
    )
  }

  // Build critical path edge set for highlighting
  const criticalEdges = new Set()
  for (let i = 0; i < criticalPath.length - 1; i++) {
    criticalEdges.add(`${criticalPath[i + 1]}->${criticalPath[i]}`)
  }

  return (
    <div className="eg-container">
      <svg
        className="eg-svg"
        width={svgSize.width}
        height={svgSize.height}
        viewBox={`0 0 ${svgSize.width} ${svgSize.height}`}
      >
        <defs>
          <marker id="eg-arrow" viewBox="0 0 10 7" refX="10" refY="3.5"
            markerWidth="8" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 3.5 L 0 7 z" fill="#555" />
          </marker>
          <marker id="eg-arrow-critical" viewBox="0 0 10 7" refX="10" refY="3.5"
            markerWidth="8" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 3.5 L 0 7 z" fill="#f59e0b" />
          </marker>
        </defs>

        {/* Edges */}
        {edges.map((edge, i) => {
          const from = positions.get(edge.from_id)
          const to = positions.get(edge.to_id)
          if (!from || !to) return null

          const isCritical = criticalEdges.has(`${edge.from_id}->${edge.to_id}`) ||
                            criticalEdges.has(`${edge.to_id}->${edge.from_id}`)

          const x1 = to.x + NODE_WIDTH
          const y1 = to.y + NODE_HEIGHT / 2
          const x2 = from.x
          const y2 = from.y + NODE_HEIGHT / 2
          const cx1 = x1 + LAYER_GAP * 0.4
          const cx2 = x2 - LAYER_GAP * 0.4

          return (
            <path
              key={i}
              d={`M ${x1} ${y1} C ${cx1} ${y1}, ${cx2} ${y2}, ${x2} ${y2}`}
              className={`eg-edge ${isCritical ? 'eg-edge--critical' : ''}`}
              markerEnd={isCritical ? 'url(#eg-arrow-critical)' : 'url(#eg-arrow)'}
            />
          )
        })}

        {/* Nodes */}
        {nodes.map(node => {
          const pos = positions.get(node.id)
          if (!pos) return null

          const colors = STATUS_COLORS[node.status] || DEFAULT_COLOR
          const isSelected = node.id === selectedNodeId
          const isHovered = node.id === hoveredId
          const isCritical = criticalSet.has(node.id)
          const isExecuting = node.status === 'executing'

          return (
            <g
              key={node.id}
              className={`eg-node ${isExecuting ? 'eg-node--executing' : ''}`}
              onClick={() => onNodeClick?.(node.id)}
              onMouseEnter={() => setHoveredId(node.id)}
              onMouseLeave={() => setHoveredId(null)}
              style={{ cursor: 'pointer' }}
            >
              <rect
                x={pos.x}
                y={pos.y}
                width={NODE_WIDTH}
                height={NODE_HEIGHT}
                rx={6}
                fill={colors.fill}
                stroke={isSelected ? '#fff' : isHovered ? '#888' : colors.stroke}
                strokeWidth={isSelected ? 2 : isCritical ? 1.5 : 1}
              />
              {/* Description */}
              <text
                x={pos.x + 8}
                y={pos.y + 18}
                fill={colors.text}
                fontSize={11}
                fontWeight={500}
              >
                {node.description?.slice(0, 22) || node.id}
              </text>
              {/* ID + complexity */}
              <text
                x={pos.x + 8}
                y={pos.y + 34}
                fill="#71717a"
                fontSize={9}
                fontFamily="monospace"
              >
                {node.id.slice(-8)}
                {node.complexity && ` [${node.complexity.toUpperCase()}]`}
              </text>
              {/* Status indicator dot */}
              <circle
                cx={pos.x + NODE_WIDTH - 14}
                cy={pos.y + NODE_HEIGHT / 2}
                r={4}
                fill={colors.stroke}
              />
            </g>
          )
        })}
      </svg>
    </div>
  )
}
