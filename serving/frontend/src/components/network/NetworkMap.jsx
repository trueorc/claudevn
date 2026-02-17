import { useMemo, useState, useRef, useCallback, useEffect, useLayoutEffect } from 'react'
import { Server, Store, Cpu, ZoomIn, ZoomOut, Maximize } from 'lucide-react'
import useCompute from '../../hooks/useCompute'
import useMarketplace from '../../hooks/useMarketplace'
import Spinner from '../common/Spinner'
import EmptyState from '../common/EmptyState'
import './NetworkMap.css'

// Zoom and pan constants
const MIN_ZOOM = 0.5
const MAX_ZOOM = 3
const ZOOM_STEP = 0.2
const INITIAL_ZOOM = 1
const INITIAL_PAN = { x: 0, y: 0 }

// Extract port from endpoint URL
function extractPort(endpoint) {
  if (!endpoint) return null
  try {
    const url = new URL(endpoint)
    return url.port || (url.protocol === 'https:' ? '443' : '80')
  } catch {
    // Try to extract port from string like "localhost:8003"
    const match = endpoint.match(/:(\d+)/)
    return match ? match[1] : null
  }
}

// Format relative time
function formatRelativeTime(timestamp) {
  if (!timestamp) return 'Unknown'
  const now = new Date()
  const then = new Date(timestamp)
  const diffMs = now - then
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 60) return `${diffSec}s ago`
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHour < 24) return `${diffHour}h ago`
  return `${diffDay}d ago`
}

function NetworkMap({ onSelectCompute, onSelectMarketplace }) {
  const { instances: computeInstances, loading: computeLoading } = useCompute({ pollInterval: 10000 })
  const { marketplaces, loading: marketplaceLoading } = useMarketplace({ pollInterval: 10000 })
  const [hoveredNode, setHoveredNode] = useState(null)
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 })

  // Zoom and pan state
  const [zoom, setZoom] = useState(INITIAL_ZOOM)
  const [pan, setPan] = useState(INITIAL_PAN)
  const [isPanning, setIsPanning] = useState(false)
  const [panStart, setPanStart] = useState({ x: 0, y: 0 })
  const hasInteractedRef = useRef(false)
  const hasFittedInitialRef = useRef(false)
  const svgRef = useRef(null)
  const containerRef = useRef(null)

  const loading = computeLoading || marketplaceLoading

  // Calculate node positions
  const layout = useMemo(() => {
    const serving = { id: 'serving', type: 'serving', x: 50, y: 50 }

    // Position marketplaces on the left (30% from left)
    const marketplaceNodes = marketplaces.map((m, i) => {
      const total = marketplaces.length
      const spacing = total > 1 ? 70 / (total + 1) : 35
      const y = 15 + spacing * (i + 1)
      return {
        id: m.marketplace_id,
        type: 'marketplace',
        data: m,
        x: 15,
        y,
        status: m.status
      }
    })

    // Position compute instances on the right (70% from left)
    const computeNodes = computeInstances.map((c, i) => {
      const total = computeInstances.length
      const spacing = total > 1 ? 70 / (total + 1) : 35
      const y = 15 + spacing * (i + 1)
      return {
        id: c.instance_id,
        type: 'compute',
        data: c,
        x: 85,
        y,
        status: c.status
      }
    })

    // Create connections from serving to all nodes
    const connections = [
      ...marketplaceNodes.map(node => ({
        from: serving,
        to: node,
        status: node.status
      })),
      ...computeNodes.map(node => ({
        from: serving,
        to: node,
        status: node.status
      }))
    ]

    return { serving, marketplaceNodes, computeNodes, connections }
  }, [marketplaces, computeInstances])

  // Calculate the zoom to fit all content in view
  const calculateFitToView = useCallback(() => {
    const { serving, marketplaceNodes, computeNodes } = layout
    const allNodes = [serving, ...marketplaceNodes, ...computeNodes]

    if (allNodes.length === 0) return { zoom: INITIAL_ZOOM, pan: INITIAL_PAN }

    // Calculate bounding box of all nodes (with padding)
    const padding = 15
    const minX = Math.min(...allNodes.map(n => n.x)) - padding
    const maxX = Math.max(...allNodes.map(n => n.x)) + padding
    const minY = Math.min(...allNodes.map(n => n.y)) - padding
    const maxY = Math.max(...allNodes.map(n => n.y)) + padding

    const contentWidth = maxX - minX
    const contentHeight = maxY - minY

    // Calculate zoom to fit content in the 100x100 viewBox
    const scaleX = 100 / contentWidth
    const scaleY = 100 / contentHeight
    const fitZoom = Math.min(scaleX, scaleY, MAX_ZOOM) * 0.9 // 90% to add margin

    // Center the content - calculate pan to center the bounding box
    const centerX = (minX + maxX) / 2
    const centerY = (minY + maxY) / 2

    // Pan needed to center content at 50,50 in the viewBox
    const fitPan = {
      x: (50 - centerX) * fitZoom,
      y: (50 - centerY) * fitZoom
    }

    return {
      zoom: Math.max(fitZoom, MIN_ZOOM),
      pan: fitPan
    }
  }, [layout])

  // Zoom handlers - zoom toward center of current view
  const handleZoomIn = useCallback(() => {
    hasInteractedRef.current = true
    setZoom(currentZoom => {
      const newZoom = Math.min(currentZoom + ZOOM_STEP, MAX_ZOOM)
      const zoomRatio = newZoom / currentZoom
      // Adjust pan to zoom toward center (50, 50 in viewBox)
      setPan(currentPan => ({
        x: currentPan.x * zoomRatio,
        y: currentPan.y * zoomRatio
      }))
      return newZoom
    })
  }, [])

  const handleZoomOut = useCallback(() => {
    hasInteractedRef.current = true
    setZoom(currentZoom => {
      const newZoom = Math.max(currentZoom - ZOOM_STEP, MIN_ZOOM)
      const zoomRatio = newZoom / currentZoom
      // Adjust pan to zoom toward center (50, 50 in viewBox)
      setPan(currentPan => ({
        x: currentPan.x * zoomRatio,
        y: currentPan.y * zoomRatio
      }))
      return newZoom
    })
  }, [])

  const handleZoomToFit = useCallback(() => {
    const { zoom: fitZoom, pan: fitPan } = calculateFitToView()
    setZoom(fitZoom)
    setPan(fitPan)
    hasInteractedRef.current = true
  }, [calculateFitToView])

  // Mouse wheel zoom - zoom toward cursor position
  const handleWheel = useCallback((e) => {
    e.preventDefault()
    hasInteractedRef.current = true

    if (!svgRef.current) return

    const rect = svgRef.current.getBoundingClientRect()

    // Get cursor position relative to SVG in viewBox coordinates (0-100)
    const cursorX = (e.clientX - rect.left) / rect.width * 100
    const cursorY = (e.clientY - rect.top) / rect.height * 100

    const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP

    setZoom(currentZoom => {
      const newZoom = Math.min(Math.max(currentZoom + delta, MIN_ZOOM), MAX_ZOOM)
      const zoomRatio = newZoom / currentZoom

      // Calculate the point in content space that cursor is over
      // With transform: translate(pan.x, pan.y) scale(zoom)
      // contentPoint = (viewBoxPoint - pan) / zoom
      setPan(currentPan => {
        const contentX = (cursorX - currentPan.x) / currentZoom
        const contentY = (cursorY - currentPan.y) / currentZoom

        // After zoom, we want the same content point to be under cursor
        // cursorX = contentX * newZoom + newPan.x
        // newPan.x = cursorX - contentX * newZoom
        const newPanX = cursorX - contentX * newZoom
        const newPanY = cursorY - contentY * newZoom

        return { x: newPanX, y: newPanY }
      })

      return newZoom
    })
  }, [])

  // Pan handlers
  const handleMouseDown = useCallback((e) => {
    // Only pan on left click and not on interactive elements
    if (e.button !== 0) return
    if (e.target.closest('.node')) return

    hasInteractedRef.current = true
    setIsPanning(true)
    // Store start position - pan values are in viewBox units, so we need to convert
    // mouse movement from pixels to viewBox units
    setPanStart({ x: e.clientX, y: e.clientY, initialPan: pan })
  }, [pan])

  const handleMouseMove = useCallback((e) => {
    if (!isPanning || !svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    // Convert pixel movement to viewBox units
    const deltaX = (e.clientX - panStart.x) / rect.width * 100
    const deltaY = (e.clientY - panStart.y) / rect.height * 100
    const newPan = {
      x: panStart.initialPan.x + deltaX,
      y: panStart.initialPan.y + deltaY
    }
    setPan(newPan)
  }, [isPanning, panStart])

  const handleMouseUp = useCallback(() => {
    setIsPanning(false)
  }, [])

  // Touch handlers for mobile/tablet
  const handleTouchStart = useCallback((e) => {
    if (e.touches.length === 1) {
      const touch = e.touches[0]
      if (e.target.closest('.node')) return
      hasInteractedRef.current = true
      setIsPanning(true)
      setPanStart({ x: touch.clientX, y: touch.clientY, initialPan: pan })
    }
  }, [pan])

  const handleTouchMove = useCallback((e) => {
    if (!isPanning || e.touches.length !== 1 || !svgRef.current) return
    const touch = e.touches[0]
    const rect = svgRef.current.getBoundingClientRect()
    // Convert pixel movement to viewBox units
    const deltaX = (touch.clientX - panStart.x) / rect.width * 100
    const deltaY = (touch.clientY - panStart.y) / rect.height * 100
    const newPan = {
      x: panStart.initialPan.x + deltaX,
      y: panStart.initialPan.y + deltaY
    }
    setPan(newPan)
  }, [isPanning, panStart])

  const handleTouchEnd = useCallback(() => {
    setIsPanning(false)
  }, [])

  // Add global mouse up listener to handle mouse release outside the SVG
  useEffect(() => {
    const handleGlobalMouseUp = () => setIsPanning(false)
    window.addEventListener('mouseup', handleGlobalMouseUp)
    window.addEventListener('touchend', handleGlobalMouseUp)
    return () => {
      window.removeEventListener('mouseup', handleGlobalMouseUp)
      window.removeEventListener('touchend', handleGlobalMouseUp)
    }
  }, [])

  // Auto fit-to-view on initial load when nodes become available
  // Using useLayoutEffect to set initial view before paint, avoiding visual flash
  useLayoutEffect(() => {
    const hasNodes = layout.computeNodes.length > 0 || layout.marketplaceNodes.length > 0
    if (!hasInteractedRef.current && !hasFittedInitialRef.current && hasNodes) {
      hasFittedInitialRef.current = true
      const { zoom: fitZoom, pan: fitPan } = calculateFitToView()
      setZoom(fitZoom)
      setPan(fitPan)
    }
  }, [layout.computeNodes.length, layout.marketplaceNodes.length, calculateFitToView])

  const getStatusClass = (status) => {
    switch (status) {
      case 'online':
      case 'healthy':
      case 'running':
        return 'status-online'
      case 'degraded':
      case 'starting':
      case 'idle':
        return 'status-degraded'
      case 'offline':
      case 'failed':
      case 'stopped':
        return 'status-offline'
      default:
        return 'status-offline'
    }
  }

  const handleNodeClick = (node) => {
    if (node.type === 'compute' && onSelectCompute) {
      onSelectCompute(node.id)
    } else if (node.type === 'marketplace' && onSelectMarketplace) {
      onSelectMarketplace(node.id)
    }
  }

  const handleNodeHover = (node, event) => {
    if (node) {
      const rect = event.currentTarget.closest('.map-svg').getBoundingClientRect()
      const x = event.clientX - rect.left
      const y = event.clientY - rect.top
      setHoveredNode(node)
      setTooltipPos({ x, y })
    } else {
      setHoveredNode(null)
    }
  }

  // Get capability counts for display
  const getComputeCapabilities = (data) => {
    const agents = data?.capabilities?.agents?.length || 0
    const tools = data?.capabilities?.tools?.length || 0
    return { agents, tools }
  }

  const getMarketplaceCapabilities = (data) => {
    const agents = data?.capabilities?.agent_count || 0
    const tools = data?.capabilities?.tool_count || 0
    return { agents, tools }
  }

  if (loading && !computeInstances.length && !marketplaces.length) {
    return (
      <div className="loading-state">
        <Spinner />
      </div>
    )
  }

  const hasNodes = computeInstances.length > 0 || marketplaces.length > 0

  if (!hasNodes) {
    return (
      <EmptyState
        icon={Server}
        title="No network nodes"
        description="Compute instances and marketplaces will appear here when they connect to serving"
      />
    )
  }

  // Calculate bezier curve path for connections
  const getBezierPath = (from, to) => {
    const x1 = from.x
    const y1 = from.y
    const x2 = to.x
    const y2 = to.y

    // Control point for quadratic bezier - push outward from center
    const centerX = 50
    const centerY = 50
    const dx = x2 - x1
    const dy = y2 - y1

    // Calculate control point perpendicular to connection, away from center
    const midX = (x1 + x2) / 2
    const midY = (y1 + y2) / 2
    const angle = Math.atan2(dy, dx)
    const perpAngle = angle + Math.PI / 2

    // Distance from center determines curve intensity
    const distFromCenter = Math.sqrt(Math.pow(midX - centerX, 2) + Math.pow(midY - centerY, 2))
    const curveIntensity = Math.min(distFromCenter * 0.15, 8)

    // Push control point away from center
    const toCenter = Math.atan2(centerY - midY, centerX - midX)
    const controlX = midX - Math.cos(toCenter) * curveIntensity
    const controlY = midY - Math.sin(toCenter) * curveIntensity

    return `M ${x1} ${y1} Q ${controlX} ${controlY} ${x2} ${y2}`
  }

  return (
    <div className="network-map" ref={containerRef}>
      {/* Zoom Controls */}
      <div className="zoom-controls">
        <button
          className="zoom-btn"
          onClick={handleZoomIn}
          title="Zoom in"
          aria-label="Zoom in"
        >
          <ZoomIn size={16} />
        </button>
        <button
          className="zoom-btn"
          onClick={handleZoomOut}
          title="Zoom out"
          aria-label="Zoom out"
        >
          <ZoomOut size={16} />
        </button>
        <button
          className="zoom-btn"
          onClick={handleZoomToFit}
          title="Zoom to fit"
          aria-label="Zoom to fit"
        >
          <Maximize size={16} />
        </button>
        <span className="zoom-level">{Math.round(zoom * 100)}%</span>
      </div>

      <svg
        ref={svgRef}
        viewBox="0 0 100 100"
        preserveAspectRatio="xMinYMin meet"
        className={`map-svg ${isPanning ? 'panning' : ''}`}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        <defs>
          {/* Gradient definitions for nodes */}
          <radialGradient id="gradient-online" cx="30%" cy="30%">
            <stop offset="0%" stopColor="#4ade80" stopOpacity="1" />
            <stop offset="100%" stopColor="#16a34a" stopOpacity="1" />
          </radialGradient>

          <radialGradient id="gradient-degraded" cx="30%" cy="30%">
            <stop offset="0%" stopColor="#fbbf24" stopOpacity="1" />
            <stop offset="100%" stopColor="#d97706" stopOpacity="1" />
          </radialGradient>

          <radialGradient id="gradient-offline" cx="30%" cy="30%">
            <stop offset="0%" stopColor="#f87171" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#dc2626" stopOpacity="0.6" />
          </radialGradient>

          <radialGradient id="gradient-serving" cx="30%" cy="30%">
            <stop offset="0%" stopColor="#a78bfa" stopOpacity="1" />
            <stop offset="100%" stopColor="#7c3aed" stopOpacity="1" />
          </radialGradient>

          {/* Arrow marker */}
          <marker
            id="arrowhead"
            markerWidth="4"
            markerHeight="4"
            refX="3"
            refY="2"
            orient="auto"
          >
            <polygon points="0 0, 4 2, 0 4" fill="var(--border-light)" />
          </marker>
        </defs>

        {/* Zoomable/pannable content wrapper */}
        <g
          className="map-content"
          transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}
        >
        {/* Connection paths with bezier curves */}
        {layout.connections.map((conn, i) => (
          <path
            key={`conn-${i}`}
            d={getBezierPath(conn.from, conn.to)}
            className={`connection ${getStatusClass(conn.status)}`}
            markerEnd="url(#arrowhead)"
          />
        ))}

        {/* Serving node (center) - enhanced with larger size and glow */}
        <g className="node serving-node" transform={`translate(${layout.serving.x}, ${layout.serving.y})`}>
          <circle r="8" className="node-circle node-serving" fill="url(#gradient-serving)" />
          <circle r="10" className="node-glow serving-glow" />
          <text y="14" className="node-label">Serving</text>
        </g>

        {/* Marketplace nodes (left side) */}
        {layout.marketplaceNodes.map(node => {
          const statusClass = getStatusClass(node.status)
          const isOnline = statusClass === 'status-online'
          const gradientId = statusClass === 'status-online' ? 'gradient-online'
            : statusClass === 'status-degraded' ? 'gradient-degraded'
            : 'gradient-offline'
          const port = extractPort(node.data.endpoint)
          const caps = getMarketplaceCapabilities(node.data)

          return (
            <g
              key={node.id}
              className={`node marketplace-node ${statusClass}`}
              transform={`translate(${node.x}, ${node.y})`}
              onClick={() => handleNodeClick(node)}
              onMouseEnter={(e) => handleNodeHover(node, e)}
              onMouseLeave={() => handleNodeHover(null)}
              style={{ cursor: 'pointer' }}
            >
              {isOnline && <circle r="6" className="node-halo" />}
              <circle r="4.5" className="node-circle" fill={`url(#${gradientId})`} />
              <text x="-7" className="node-label node-label-left">{node.data.name || node.id.slice(0, 8)}</text>
              {port && <text x="-7" y="3" className="node-sublabel node-label-left">:{port}</text>}
              {(caps.agents > 0 || caps.tools > 0) && (
                <text x="-7" y="6" className="node-caps node-label-left">
                  {caps.agents > 0 && `${caps.agents}A`}{caps.agents > 0 && caps.tools > 0 && ' '}{caps.tools > 0 && `${caps.tools}T`}
                </text>
              )}
            </g>
          )
        })}

        {/* Compute nodes (right side) */}
        {layout.computeNodes.map(node => {
          const statusClass = getStatusClass(node.status)
          const isOnline = statusClass === 'status-online'
          const gradientId = statusClass === 'status-online' ? 'gradient-online'
            : statusClass === 'status-degraded' ? 'gradient-degraded'
            : 'gradient-offline'
          const port = extractPort(node.data.endpoint)
          const caps = getComputeCapabilities(node.data)

          return (
            <g
              key={node.id}
              className={`node compute-node ${statusClass}`}
              transform={`translate(${node.x}, ${node.y})`}
              onClick={() => handleNodeClick(node)}
              onMouseEnter={(e) => handleNodeHover(node, e)}
              onMouseLeave={() => handleNodeHover(null)}
              style={{ cursor: 'pointer' }}
            >
              {isOnline && <circle r="6" className="node-halo" />}
              <circle r="4.5" className="node-circle" fill={`url(#${gradientId})`} />
              <text x="7" className="node-label node-label-right">{node.data.name || node.id.slice(0, 8)}</text>
              {port && <text x="7" y="3" className="node-sublabel node-label-right">:{port}</text>}
              {(caps.agents > 0 || caps.tools > 0) && (
                <text x="7" y="6" className="node-caps node-label-right">
                  {caps.agents > 0 && `${caps.agents}A`}{caps.agents > 0 && caps.tools > 0 && ' '}{caps.tools > 0 && `${caps.tools}T`}
                </text>
              )}
            </g>
          )
        })}
        </g>
      </svg>

      {/* Hover tooltip */}
      {hoveredNode && hoveredNode.type !== 'serving' && (
        <div
          className="node-tooltip"
          style={{
            left: tooltipPos.x,
            top: tooltipPos.y,
          }}
        >
          <div className="tooltip-header">
            {hoveredNode.type === 'compute' ? <Cpu size={12} /> : <Store size={12} />}
            <span>{hoveredNode.data.name || hoveredNode.id}</span>
          </div>
          <div className="tooltip-row">
            <span className="tooltip-label">ID:</span>
            <span className="tooltip-value">{hoveredNode.id.slice(0, 12)}...</span>
          </div>
          <div className="tooltip-row">
            <span className="tooltip-label">Endpoint:</span>
            <span className="tooltip-value">{hoveredNode.data.endpoint || 'N/A'}</span>
          </div>
          <div className="tooltip-row">
            <span className="tooltip-label">Status:</span>
            <span className={`tooltip-status ${getStatusClass(hoveredNode.status)}`}>
              {hoveredNode.status}
            </span>
          </div>
          {hoveredNode.data.version && (
            <div className="tooltip-row">
              <span className="tooltip-label">Version:</span>
              <span className="tooltip-value">{hoveredNode.data.version}</span>
            </div>
          )}
          <div className="tooltip-row">
            <span className="tooltip-label">Last seen:</span>
            <span className="tooltip-value">{formatRelativeTime(hoveredNode.data.last_heartbeat)}</span>
          </div>
          {hoveredNode.type === 'compute' && (
            <>
              {hoveredNode.data.capabilities?.agents?.length > 0 && (
                <div className="tooltip-row">
                  <span className="tooltip-label">Agents:</span>
                  <span className="tooltip-value">{hoveredNode.data.capabilities.agents.join(', ')}</span>
                </div>
              )}
              {hoveredNode.data.capabilities?.labels?.length > 0 && (
                <div className="tooltip-row">
                  <span className="tooltip-label">Labels:</span>
                  <span className="tooltip-value">{hoveredNode.data.capabilities.labels.join(', ')}</span>
                </div>
              )}
            </>
          )}
          {hoveredNode.type === 'marketplace' && hoveredNode.data.capabilities && (
            <div className="tooltip-row">
              <span className="tooltip-label">Catalog:</span>
              <span className="tooltip-value">
                {hoveredNode.data.capabilities.agent_count || 0} agents, {hoveredNode.data.capabilities.tool_count || 0} tools
              </span>
            </div>
          )}
          <div className="tooltip-hint">Click for details</div>
        </div>
      )}

      {/* Legend */}
      <div className="map-legend">
        <div className="legend-section">
          <span className="legend-title">Nodes</span>
          <div className="legend-item">
            <Server size={12} />
            <span>Serving</span>
          </div>
          <div className="legend-item">
            <Store size={12} />
            <span>Skills</span>
          </div>
          <div className="legend-item">
            <Cpu size={12} />
            <span>Compute</span>
          </div>
        </div>
        <div className="legend-section">
          <span className="legend-title">Status</span>
          <div className="legend-item">
            <span className="legend-dot status-online"></span>
            <span>Online</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot status-degraded"></span>
            <span>Degraded</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot status-offline"></span>
            <span>Offline</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default NetworkMap
