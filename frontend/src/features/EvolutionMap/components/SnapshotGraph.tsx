import { useState, useCallback, forwardRef, useImperativeHandle, useEffect, useMemo } from 'react'
import type { LayoutNode } from '../layout/radialLayout'

interface SnapshotGraphProps {
  layout: LayoutNode[]
  activeSnapshotId: string | null
  clusterCounts: Map<string, number>
  onNodeClick: (nodeId: string) => void
  width: number
  height: number
}

export interface SnapshotGraphHandle {
  reset: () => void
}

const NODE_R = 32
const LABEL_LINE_HEIGHT = 11

function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

/**
 * SVG-based tree graph of cluster snapshot history. Root sits at the top,
 * descendants flow downward in levels. The active snapshot is filled with
 * --color-primary; others are outlined. Supports zoom (wheel) and exposes a
 * `reset()` imperative handle that restores the fit-to-view framing.
 *
 * @param layout           - Tree layout nodes.
 * @param activeSnapshotId - Currently active snapshot UUID.
 * @param clusterCounts    - Map from node ID to number of clusters.
 * @param onNodeClick      - Called with node ID when clicked.
 * @param onDeleteRequest  - Called with LayoutNode when trash icon is clicked.
 * @param width            - Container width.
 * @param height           - Container height.
 */
export const SnapshotGraph = forwardRef<SnapshotGraphHandle, SnapshotGraphProps>(
  function SnapshotGraph(
    { layout, activeSnapshotId, clusterCounts, onNodeClick, width, height },
    ref,
  ) {
    const [scale, setScale] = useState(1)
    const [hoveredId, setHoveredId] = useState<string | null>(null)

    const bounds = useMemo(() => {
      if (layout.length === 0) {
        return { minX: 0, maxX: 1, minY: 0, maxY: 1 }
      }

      const labelPadding = NODE_R + 8
      const xs = layout.map((node) => node.x)
      const ys = layout.map((node) => node.y)

      return {
        minX: Math.min(...xs) - labelPadding,
        maxX: Math.max(...xs) + labelPadding,
        minY: Math.min(...ys) - NODE_R - 4,
        maxY: Math.max(...ys) + NODE_R + LABEL_LINE_HEIGHT + 4,
      }
    }, [layout])

    const graphWidth = Math.max(bounds.maxX - bounds.minX, 1)
    const graphHeight = Math.max(bounds.maxY - bounds.minY, 1)
    const fitScale = Math.min(width / graphWidth, height / graphHeight)

    const transform = useMemo(() => {
      const x = (width - graphWidth * scale) / 2 - bounds.minX * scale
      const y = (height - graphHeight * scale) / 2 - bounds.minY * scale
      return { x, y }
    }, [bounds.minX, bounds.minY, graphHeight, graphWidth, height, scale, width])

    useEffect(() => {
      setScale(fitScale)
    }, [fitScale])

    useImperativeHandle(ref, () => ({
      reset: () => setScale(fitScale),
    }))

    const handleWheel = useCallback((e: React.WheelEvent) => {
      e.preventDefault()
      setScale((current) => {
        const next = current * (e.deltaY < 0 ? 1.1 : 0.9)
        return Math.max(0.05, Math.min(fitScale, next))
      })
    }, [fitScale])

    const hoveredNode = hoveredId ? layout.find((n) => n.id === hoveredId) : null

    return (
      <div className="relative select-none overflow-hidden" style={{ width, height }}>
        <svg
          width={width}
          height={height}
          style={{ cursor: 'default' }}
          onWheel={handleWheel}
        >
          <g transform={`translate(${transform.x}, ${transform.y}) scale(${scale})`}>
            {/* Edges */}
            {layout
              .filter((n) => n.parent_id !== null)
              .map((n) => {
                const parent = layout.find((p) => p.id === n.parent_id)
                if (!parent) return null
                return (
                  <line
                    key={`edge-${n.id}`}
                    x1={parent.x}
                    y1={parent.y}
                    x2={n.x}
                    y2={n.y}
                    stroke="var(--color-border)"
                    strokeWidth={1.5}
                  />
                )
              })}

            {/* Nodes */}
            {layout.map((n) => {
              const isActive = n.id === activeSnapshotId
              const isHovered = n.id === hoveredId
              const opLabel = n.operation === 'base' ? 'base' : n.operation.replace('_', ' ')
              const indexLabel = n.operation === 'base' ? '' : `#${n.sopIndex}`

              return (
                <g
                  key={n.id}
                  data-node="true"
                  style={{ cursor: 'pointer' }}
                  onClick={() => onNodeClick(n.id)}
                  onMouseEnter={() => setHoveredId(n.id)}
                  onMouseLeave={() => setHoveredId(null)}
                >
                  {isHovered && (
                    <circle cx={n.x} cy={n.y} r={NODE_R + 6} fill="var(--color-primary)" opacity={0.15} />
                  )}
                  <circle
                    cx={n.x}
                    cy={n.y}
                    r={NODE_R}
                    fill={isActive ? 'var(--color-primary)' : 'var(--color-surface)'}
                    stroke={isActive ? 'var(--color-primary)' : 'var(--color-border)'}
                    strokeWidth={isActive ? 2 : 1.5}
                  />
                  <text
                    x={n.x}
                    y={n.y - (indexLabel ? LABEL_LINE_HEIGHT / 2 : 0)}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize={9}
                    fontFamily="Inter, system-ui, sans-serif"
                    fill={isActive ? 'var(--color-surface)' : 'var(--color-text)'}
                    style={{ pointerEvents: 'none', userSelect: 'none' }}
                  >
                    {opLabel}
                  </text>
                  {indexLabel && (
                    <text
                      x={n.x}
                      y={n.y + LABEL_LINE_HEIGHT / 2 + 2}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fontSize={9}
                      fontFamily="Inter, system-ui, sans-serif"
                      fill={isActive ? 'var(--color-surface)' : 'var(--color-muted)'}
                      style={{ pointerEvents: 'none', userSelect: 'none' }}
                    >
                      {indexLabel}
                    </text>
                  )}
                </g>
              )
            })}
          </g>
        </svg>

        {/* Hover tooltip card — positioned in screen space */}
        {hoveredNode && (() => {
          const svgX = (hoveredNode.x * scale) + transform.x
          const svgY = (hoveredNode.y * scale) + transform.y
          return (
            <div
              className="absolute z-10 pointer-events-auto"
              style={{ left: svgX + NODE_R + 8, top: svgY - 36 }}
              onMouseEnter={() => setHoveredId(hoveredNode.id)}
              onMouseLeave={() => setHoveredId(null)}
            >
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 shadow-lg text-xs min-w-[130px]">
                <p className="font-medium text-[var(--color-text)] capitalize">
                  {hoveredNode.operation === 'base'
                    ? 'Base snapshot'
                    : `${hoveredNode.operation.replace('_', ' ')} #${hoveredNode.sopIndex}`}
                </p>
                <p className="text-[var(--color-muted)] mt-0.5">{formatRelativeTime(hoveredNode.created_at)}</p>
                <p className="text-[var(--color-muted)]">{clusterCounts.get(hoveredNode.id) ?? 0} clusters</p>
              </div>
            </div>
          )
        })()}
      </div>
    )
  },
)
