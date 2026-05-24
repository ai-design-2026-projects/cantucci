import { forwardRef, useImperativeHandle } from 'react'
import type { LayoutNode } from '../lib/radialLayout'
import { relativeTime } from '@/lib/utils'
import { LABEL_LINE_HEIGHT, NODE_R, formatSnapshotIndexLabel, formatSnapshotOperationLabel, formatSnapshotTooltipTitle } from '../lib/snapshotGraph.ts'
import { useSnapshotGraphData } from '../hooks/useSnapshotGraphData.ts'
import { useSnapshotGraphHandlers } from '../hooks/useSnapshotGraphHandlers.ts'

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
    const { fitScale, transform } = useSnapshotGraphData(layout, width, height)
    const { scale, hoveredId, hoveredNode, setHoveredId, handleWheel, resetScale } = useSnapshotGraphHandlers(layout, fitScale)

    useImperativeHandle(ref, () => ({
      reset: resetScale,
    }))

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
              const opLabel = formatSnapshotOperationLabel(n.operation)
              const indexLabel = formatSnapshotIndexLabel(n.operation, n.sopIndex)

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
                <p className="font-medium text-[var(--color-text)] capitalize">{formatSnapshotTooltipTitle(hoveredNode)}</p>
                <p className="text-[var(--color-muted)] mt-0.5">{relativeTime(hoveredNode.created_at)}</p>
                <p className="text-[var(--color-muted)]">{clusterCounts.get(hoveredNode.id) ?? 0} clusters</p>
              </div>
            </div>
          )
        })()}
      </div>
    )
  },
)
