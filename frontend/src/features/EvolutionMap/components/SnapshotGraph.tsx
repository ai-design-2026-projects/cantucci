import { useState, useRef, useCallback, forwardRef, useImperativeHandle } from 'react'
import type { LayoutNode } from '../layout/radialLayout'

interface SnapshotGraphProps {
  layout: LayoutNode[]
  activeSnapshotId: string | null
  childCounts: Map<string, number>
  onNodeClick: (nodeId: string) => void
  width: number
  height: number
}

export interface SnapshotGraphHandle {
  reset: () => void
}

const NODE_R = 22
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
 * SVG-based radial graph of cluster snapshot history. Root sits at center,
 * descendants fan out in concentric rings. The active snapshot is filled with
 * --color-primary; others are outlined. Supports pan (drag) and zoom (wheel).
 * Expose a `reset()` imperative handle to recenter the view.
 *
 * @param nodes            - Snapshot DAG nodes.
 * @param activeSnapshotId - Currently active snapshot UUID.
 * @param childCounts      - Map from node ID to number of children.
 * @param onNodeClick      - Called with node ID when clicked.
 * @param onDeleteRequest  - Called with LayoutNode when trash icon is clicked.
 * @param width            - Container width.
 * @param height           - Container height.
 */
export const SnapshotGraph = forwardRef<SnapshotGraphHandle, SnapshotGraphProps>(
  function SnapshotGraph(
    { layout, activeSnapshotId, childCounts, onNodeClick, width, height },
    ref,
  ) {
    const [view, setView] = useState({ x: 0, y: 0, scale: 1 })
    const [hoveredId, setHoveredId] = useState<string | null>(null)
    const dragging = useRef(false)
    const dragStart = useRef({ mx: 0, my: 0, vx: 0, vy: 0 })

    const centerX = width / 2
    const centerY = height / 2

    useImperativeHandle(ref, () => ({
      reset: () => setView({ x: 0, y: 0, scale: 1 }),
    }))

    const handleWheel = useCallback((e: React.WheelEvent) => {
      e.preventDefault()
      setView((v) => ({
        ...v,
        scale: Math.max(0.25, Math.min(4, v.scale * (e.deltaY < 0 ? 1.1 : 0.9))),
      }))
    }, [])

    const handleMouseDown = useCallback(
      (e: React.MouseEvent) => {
        if ((e.target as Element).closest('[data-node]')) return
        dragging.current = true
        dragStart.current = { mx: e.clientX, my: e.clientY, vx: view.x, vy: view.y }
      },
      [view.x, view.y],
    )

    const handleMouseMove = useCallback((e: React.MouseEvent) => {
      if (!dragging.current) return
      setView((v) => ({
        ...v,
        x: dragStart.current.vx + (e.clientX - dragStart.current.mx),
        y: dragStart.current.vy + (e.clientY - dragStart.current.my),
      }))
    }, [])

    const handleMouseUp = useCallback(() => {
      dragging.current = false
    }, [])

    const hoveredNode = hoveredId ? layout.find((n) => n.id === hoveredId) : null

    return (
      <div className="relative select-none overflow-hidden" style={{ width, height }}>
        <svg
          width={width}
          height={height}
          style={{ cursor: 'grab' }}
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          <g transform={`translate(${centerX + view.x}, ${centerY + view.y}) scale(${view.scale})`}>
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
          const svgX = (hoveredNode.x * view.scale) + centerX + view.x
          const svgY = (hoveredNode.y * view.scale) + centerY + view.y
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
                <p className="text-[var(--color-muted)]">{childCounts.get(hoveredNode.id) ?? 0} children</p>
              </div>
            </div>
          )
        })()}
      </div>
    )
  },
)
