import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { clusterColorFromUuid } from '@/styles/theme'
import { useThemeStore } from '@/store/useThemeStore'
import type { ClusterSnapshotDto, ScatterPoint } from '@/lib/types'

interface SnapshotPlotProps {
  points: ScatterPoint[]
  snapshot: ClusterSnapshotDto
  selectedClusterId: string | null
  onPointClick: (movieId: number) => void
}

interface CustomDotProps {
  cx?: number
  cy?: number
  fill?: string
  payload?: ScatterPoint
}

function CustomDot({ cx = 0, cy = 0, fill = '#ccc', payload, onPointClick, dimmed }: CustomDotProps & { onPointClick: (id: number) => void; dimmed: boolean }) {
  return (
    <circle
      cx={cx}
      cy={cy}
      r={5}
      fill={fill}
      opacity={dimmed ? 0.2 : 0.85}
      stroke={fill}
      strokeWidth={1}
      style={{ cursor: 'pointer', transition: 'opacity 0.2s' }}
      onClick={() => payload && onPointClick(payload.movieId)}
    />
  )
}

/**
 * 2D scatter plot of all exemplar movies across clusters, color-coded by cluster.
 * Clicking a point opens the movie detail popup; clicking a cluster dims the others.
 *
 * @param points           - ScatterPoint array with x/y UMAP coords and cluster info.
 * @param snapshot         - Active snapshot (used to look up cluster objects).
 * @param selectedClusterId - When set, dims all clusters except this one.
 * @param onPointClick     - Called with the TMDB movie ID when a point is clicked.
 * @returns Responsive scatter chart.
 */
export function SnapshotPlot({ points, snapshot, selectedClusterId, onPointClick }: SnapshotPlotProps) {
  const isDark = useThemeStore((s) => s.theme === 'dark')

  const byCluster = snapshot.clusters.reduce<Record<string, ScatterPoint[]>>((acc, c) => {
    acc[c.id] = points.filter((p) => p.clusterId === c.id)
    return acc
  }, {})

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <XAxis dataKey="x" hide />
        <YAxis dataKey="y" hide />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.[0]) return null
            const p = payload[0].payload as ScatterPoint
            return (
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-1.5 text-xs text-[var(--color-text)] shadow-md">
                {p.title}
                {p.clusterLabel && (
                  <span className="text-[var(--color-muted)] ml-2">{p.clusterLabel}</span>
                )}
              </div>
            )
          }}
        />
        {snapshot.clusters.map((cluster) => {
          const color = clusterColorFromUuid(cluster.id, isDark)
          const dimmed = selectedClusterId !== null && selectedClusterId !== cluster.id
          return (
            <Scatter
              key={cluster.id}
              name={cluster.label ?? cluster.id}
              data={byCluster[cluster.id] ?? []}
              fill={color}
              shape={(props: CustomDotProps) => (
                <CustomDot
                  {...props}
                  fill={color}
                  onPointClick={onPointClick}
                  dimmed={dimmed}
                />
              )}
            />
          )
        })}
      </ScatterChart>
    </ResponsiveContainer>
  )
}
