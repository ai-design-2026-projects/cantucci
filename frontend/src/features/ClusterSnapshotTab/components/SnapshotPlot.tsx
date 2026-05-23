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
import type { ClusterSnapshotDto } from '@/api/dto/snapshots'
import type { ScatterPoint } from '../hooks/useScatterData.ts'
import { CustomDot } from './CustomDot.tsx'
import { useSnapshotPlotData } from '../hooks/useSnapshotPlotData.ts'

/**
 * 2D scatter plot of all exemplar movies across clusters, color-coded by cluster.
 * When dimmedAll is true (no active conversation), all dots are rendered grey as a
 * silhouette of the corpus. Clicking a point opens the movie detail popup.
 *
 * @param points            - ScatterPoint array with x/y UMAP coords and cluster info.
 * @param snapshot          - Active snapshot (used to look up cluster objects).
 * @param selectedClusterId - When set, dims all clusters except this one.
 * @param onPointClick      - Called with the TMDB movie ID when a point is clicked.
 * @param dimmedAll         - When true, renders all points in muted grey (welcome screen).
 * @returns Responsive scatter chart with dot-grid background.
 */
export function SnapshotPlot({
	points,
	snapshot,
	selectedClusterId,
	onPointClick,
	dimmedAll = false,
	baseDomain,
}: {
	points: ScatterPoint[]
	snapshot: ClusterSnapshotDto
	selectedClusterId: string | null
	onPointClick: (movieId: number) => void
	dimmedAll?: boolean
	baseDomain?: { x: [number, number]; y: [number, number] }
}) {
	const isDark = useThemeStore((s) => s.theme === 'dark')
	const { xDomain, yDomain, byCluster } = useSnapshotPlotData(points, snapshot, baseDomain)

	return (
		<div className="relative w-full h-full">
			{/* Dot grid background layer at low opacity */}
			<div
				className="absolute inset-0 pointer-events-none"
				style={{
					backgroundImage: 'radial-gradient(var(--color-border) 1px, transparent 1px)',
					backgroundSize: '14px 14px',
					opacity: 0.35,
				}}
			/>
			<ResponsiveContainer width="100%" height="100%">
				<ScatterChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
					<XAxis dataKey="x" type="number" domain={xDomain} hide />
					<YAxis dataKey="y" type="number" domain={yDomain} hide />
					<Tooltip
						content={({ active, payload }) => {
							if (!active || !payload?.[0]) return null
							const p = payload[0].payload as ScatterPoint
							return (
								<div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-1.5 text-xs text-[var(--color-text)] shadow-md">
									<p className="font-medium">{p.title}</p>
									{p.clusterLabel && (
										<p className="text-[var(--color-muted)] mt-0.5">{p.clusterLabel}</p>
									)}
								</div>
							)
						}}
					/>
					{dimmedAll ? (
						<Scatter
							data={points}
							fill="var(--color-muted)"
							opacity={0.4}
							shape={({ cx = 0, cy = 0 }: { cx?: number; cy?: number }) => (
								<circle
									cx={cx}
									cy={cy}
									r={4}
									fill="var(--color-muted)"
									opacity={0.4}
								/>
							)}
							isAnimationActive={false}
						/>
					) : (
						snapshot.clusters.map((cluster) => {
							const color = clusterColorFromUuid(cluster.id, isDark)
							const dimmed = selectedClusterId !== null && selectedClusterId !== cluster.id
							return (
								<Scatter
									key={cluster.id}
									name={cluster.label ?? cluster.id}
									data={byCluster[cluster.id] ?? []}
									fill={color}
									animationDuration={400}
									shape={({ cx, cy, fill }: { cx?: number; cy?: number; fill?: string }) => (
										<CustomDot
											cx={cx}
											cy={cy}
											fill={fill ?? color}
											onPointClick={onPointClick}
											dimmed={dimmed}
										/>
									)}
								/>
							)
						})
					)}
				</ScatterChart>
			</ResponsiveContainer>
		</div>
	)
}
