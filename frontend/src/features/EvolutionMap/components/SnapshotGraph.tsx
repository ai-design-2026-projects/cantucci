import { forwardRef, useImperativeHandle } from 'react'
import type { LayoutNode } from '../lib/radialLayout'
import { relativeTime } from '@/lib/utils'
import { LABEL_LINE_HEIGHT, NODE_R, formatSnapshotIndexLabel, formatSnapshotOperationLines, formatSnapshotTooltipTitle } from '../lib/snapshotGraph.ts'
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
 * --color-primary; others are outlined. Supports wheel zoom (up to 4×),
 * drag-to-pan, and exposes a `reset()` imperative handle that restores
 * the capped fit-to-view framing.
 *
 * @param layout           - Tree layout nodes.
 * @param activeSnapshotId - Currently active snapshot UUID.
 * @param clusterCounts    - Map from node ID to number of clusters.
 * @param onNodeClick      - Called with node ID when clicked.
 * @param width            - Container width.
 * @param height           - Container height.
 */
export const SnapshotGraph = forwardRef<SnapshotGraphHandle, SnapshotGraphProps>(
  function SnapshotGraph(
    { layout, activeSnapshotId, clusterCounts, onNodeClick, width, height },
    ref,
  ) {
    const { fitScale, transform, graphWidth, graphHeight } = useSnapshotGraphData(layout, width, height)
    const {
      scale,
      pan,
      isDragging,
      dragRef,
      hoveredId,
      hoveredNode,
      setHoveredId,
      handleWheel,
      handleMouseDown,
      handleMouseMove,
      handleMouseUp,
      handleMouseLeave,
      resetScale,
    } = useSnapshotGraphHandlers(layout, fitScale, graphWidth, graphHeight, width, height)

    useImperativeHandle(ref, () => ({
      reset: resetScale,
    }))

    return (
      <div className="relative select-none overflow-hidden" style={{ width, height }}>
        <svg
          width={width}
          height={height}
          style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
        >
          <g transform={`translate(${transform.x + pan.x}, ${transform.y + pan.y}) scale(${scale})`}>
            <defs>
              {layout.map((n) => (
                <clipPath key={`clip-${n.id}`} id={`clip-${n.id}`}>
                  <circle cx={n.x} cy={n.y} r={NODE_R - 2} />
                </clipPath>
              ))}
            </defs>

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
              const isUnclustered = n.operation === 'unclustered'
              const isActive = n.id === activeSnapshotId
              const isHovered = n.id === hoveredId
              const opLines = formatSnapshotOperationLines(n)
              const indexLabel = formatSnapshotIndexLabel(n.operation, n.sopIndex)
              const blockCenterY = n.y - (indexLabel ? LABEL_LINE_HEIGHT / 2 : 0)
              const firstLineY = blockCenterY - ((opLines.length - 1) * LABEL_LINE_HEIGHT) / 2

              const circleFill = isActive ? 'var(--color-primary)' : 'var(--color-surface)'
              const circleStroke = isActive ? 'var(--color-primary)' : 'var(--color-border)'
              const textFill = isActive ? 'var(--color-surface)' : (isUnclustered ? 'var(--color-muted)' : 'var(--color-text)')
              const paramFill = isActive ? 'rgba(255,255,255,0.65)' : 'var(--color-muted)'

              return (
                <g
                  key={n.id}
                  data-node="true"
                  data-operation={n.operation}
                  data-snapshot-id={n.id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => { if (!dragRef.current.moved) onNodeClick(n.id) }}
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
                    fill={circleFill}
                    stroke={circleStroke}
                    strokeWidth={isActive ? 2 : 1.5}
                    strokeDasharray={isUnclustered && !isActive ? '4 3' : undefined}
                  />
                  <text
                    textAnchor="middle"
                    fontFamily="Inter, system-ui, sans-serif"
                    clipPath={`url(#clip-${n.id})`}
                    style={{ pointerEvents: 'none', userSelect: 'none' }}
                  >
                    {opLines.map((line, i) => (
                      <tspan
                        key={i}
                        x={n.x}
                        y={firstLineY + i * LABEL_LINE_HEIGHT}
                        dominantBaseline="middle"
                        fontSize={i === 0 ? 10 : 8}
                        fontWeight={i === 0 ? 700 : 400}
                        fill={i === 0 ? textFill : paramFill}
                      >
                        {line}
                      </tspan>
                    ))}
                  </text>
                  {indexLabel && (
                    <text
                      x={n.x}
                      y={blockCenterY + (opLines.length * LABEL_LINE_HEIGHT) / 2 + 2}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fontSize={8}
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
          const svgX = (hoveredNode.x * scale) + transform.x + pan.x
          const svgY = (hoveredNode.y * scale) + transform.y + pan.y
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
