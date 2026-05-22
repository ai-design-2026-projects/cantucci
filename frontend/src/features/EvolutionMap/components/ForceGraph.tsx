import { useCallback, useRef, useEffect } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { clusterColorFromUuid } from '@/styles/theme'
import { useThemeStore } from '@/store/useThemeStore'
import { OPERATION_LABELS } from '@/lib/constants'
import type { ClusterSnapshotGraphNode } from '@/lib/types'

interface NodeObject {
  id: string
  label: string
  color: string
  x?: number
  y?: number
}

interface LinkObject {
  source: string
  target: string
}

interface ForceGraphProps {
  nodes: ClusterSnapshotGraphNode[]
  activeSnapshotId: string | null
  onNodeClick: (nodeId: string) => void
  width: number
  height: number
}

/**
 * Force-directed graph of cluster snapshot history.
 * Nodes are colored by snapshot UUID, labeled by operation, and the active
 * snapshot gets a glow ring. Click a node to switch active snapshot.
 *
 * @param nodes            - Snapshot DAG nodes.
 * @param activeSnapshotId - Currently active snapshot UUID.
 * @param onNodeClick      - Called with node ID when clicked.
 * @param onDeleteNode     - Called with node ID when the delete icon is clicked.
 * @param width            - Canvas width in pixels.
 * @param height           - Canvas height in pixels.
 * @returns Force-directed graph canvas.
 */
export function ForceGraph({ nodes, activeSnapshotId, onNodeClick, width, height }: ForceGraphProps) {
  const isDark = useThemeStore((s) => s.theme === 'dark')
  const fgRef = useRef<any>(null)

  const graphData = {
    nodes: nodes.map((n): NodeObject => ({
      id: n.id,
      label: OPERATION_LABELS[n.operation] ?? n.operation,
      color: clusterColorFromUuid(n.id, isDark),
    })),
    links: nodes
      .filter((n) => n.parent_id !== null)
      .map((n): LinkObject => ({
        source: n.parent_id as string,
        target: n.id,
      })),
  }

  const paintNode = useCallback(
    (node: NodeObject, ctx: CanvasRenderingContext2D) => {
      const x = node.x ?? 0
      const y = node.y ?? 0
      const r = 14
      const isActive = node.id === activeSnapshotId

      if (isActive) {
        ctx.beginPath()
        ctx.arc(x, y, r + 5, 0, 2 * Math.PI)
        ctx.fillStyle = isDark ? 'rgba(255,143,163,0.3)' : 'rgba(217,78,106,0.25)'
        ctx.fill()
      }

      ctx.beginPath()
      ctx.arc(x, y, r, 0, 2 * Math.PI)
      ctx.fillStyle = node.color
      ctx.fill()

      ctx.font = '9px Inter, sans-serif'
      ctx.fillStyle = isDark ? '#f5ecef' : '#1a0f1f'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(node.label, x, y + r + 9)
    },
    [activeSnapshotId, isDark],
  )

  useEffect(() => {
    if (fgRef.current) {
      setTimeout(() => fgRef.current?.zoomToFit(300, 40), 200)
    }
  }, [nodes.length])

  return (
    <ForceGraph2D
      ref={fgRef}
      graphData={graphData}
      width={width}
      height={height}
      backgroundColor={isDark ? '#2a1830' : '#faf6f4'}
      linkColor={() => isDark ? '#4a2a48' : '#e8d5db'}
      linkWidth={1.5}
      nodeCanvasObject={paintNode}
      nodePointerAreaPaint={(node: NodeObject, color: string, ctx: CanvasRenderingContext2D) => {
        ctx.beginPath()
        ctx.arc(node.x ?? 0, node.y ?? 0, 14, 0, 2 * Math.PI)
        ctx.fillStyle = color
        ctx.fill()
      }}
      onNodeClick={(node: NodeObject) => onNodeClick(node.id)}
    />
  )
}
