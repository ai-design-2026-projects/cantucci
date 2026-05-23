import { useMemo } from 'react'
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
import type { ScatterPoint } from '../hooks/useScatterData'

interface SnapshotPlotProps {
	points: ScatterPoint[]
	snapshot: ClusterSnapshotDto
	selectedClusterId: string | null
	onPointClick: (movieId: number) => void
	dimmedAll?: boolean
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
export function SnapshotPlot({ points, snapshot, selectedClusterId, onPointClick, dimmedAll = false }: SnapshotPlotProps) {
	const isDark = useThemeStore((s) => s.theme === 'dark')

	const { xDomain, yDomain } = useMemo(() => {
		if (points.length === 0) return { xDomain: [0, 1] as [number, number], yDomain: [0, 1] as [number, number] }
		const xs = points.map((p) => p.x)
		const ys = points.map((p) => p.y)
		const xMin = Math.min(...xs)
		const xMax = Math.max(...xs)
		const yMin = Math.min(...ys)
		const yMax = Math.max(...ys)
		const xPad = (xMax - xMin) * 0.05 || 1
		const yPad = (yMax - yMin) * 0.05 || 1
		return {
			xDomain: [xMin - xPad, xMax + xPad] as [number, number],
			yDomain: [yMin - yPad, yMax + yPad] as [number, number],
		}
	}, [points])

	const byCluster = snapshot.clusters.reduce<Record<string, ScatterPoint[]>>((acc, c) => {
		acc[c.id] = points.filter((p) => p.clusterId === c.id)
		return acc
	}, {})

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
					{!dimmedAll && (
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
					)}
					{dimmedAll ? (
						<Scatter
							data={points}
							fill="var(--color-muted)"
							opacity={0.4}
							shape={(props: CustomDotProps) => (
								<circle
									cx={props.cx ?? 0}
									cy={props.cy ?? 0}
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
						})
					)}
				</ScatterChart>
			</ResponsiveContainer>
		</div>
	)
}
