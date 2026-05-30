import type { AxisPointDto } from '@/api/dto/concepts'

export interface BeeswarmPoint {
    movie_id: number
    title: string
    score: number
    /** Jittered vertical offset in [-1, 1] — no semantic meaning, purely for spacing. */
    y: number
    vote_count: number
    /** Whether this movie is a pole-representative highlight. */
    isPolestar: boolean
}

const BINS = 60
const MAX_HALF_BAND = 0.45
const POLESTAR_N = 6

/** Deterministic per-movie jitter so the layout is stable across renders. */
function stableRandom(seed: number): number {
    const x = Math.sin(seed * 9301 + 49297) * 233280
    return x - Math.floor(x)
}

/**
 * Lay out scored movies as a beeswarm with density-proportional vertical jitter.
 *
 * The vertical band at each x-position is scaled to the local point density:
 * the busiest bin gets the full MAX_HALF_BAND spread, sparser bins scale down
 * proportionally. This creates an organic swarm silhouette whose width reflects
 * the distribution without using the y-axis for data.
 *
 * Pole-representative movies (high |score| AND high vote_count) are flagged
 * with `isPolestar` so the chart can render them distinctly.
 *
 * @param points - Scored movie points from the API (any order).
 * @returns Points augmented with a stable jittered `y` and `isPolestar` flag.
 */
export function computeBeeswarm(points: AxisPointDto[]): BeeswarmPoint[] {
    if (points.length === 0) return []

    const binWidth = 2 / BINS
    const counts = new Array<number>(BINS).fill(0)
    for (const p of points) {
        const idx = Math.min(Math.floor((p.score + 1) / binWidth), BINS - 1)
        counts[idx]++
    }
    const maxCount = Math.max(...counts, 1)

    const maxVoteCount = Math.max(...points.map((p) => p.vote_count), 1)

    // Prominence weights vote_count heavily (squared) so only truly famous movies near a pole qualify
    const withProminence = points.map((p) => ({
        ...p,
        prominence: Math.abs(p.score) * (p.vote_count / maxVoteCount) ** 2,
    }))

    // Top POLESTAR_N from positive pole and POLESTAR_N from negative pole
    const positiveStars = new Set(
        [...withProminence]
            .filter((p) => p.score > 0)
            .sort((a, b) => b.prominence - a.prominence)
            .slice(0, POLESTAR_N)
            .map((p) => p.movie_id),
    )
    const negativeStars = new Set(
        [...withProminence]
            .filter((p) => p.score < 0)
            .sort((a, b) => b.prominence - a.prominence)
            .slice(0, POLESTAR_N)
            .map((p) => p.movie_id),
    )

    return points.map((p) => {
        const idx = Math.min(Math.floor((p.score + 1) / binWidth), BINS - 1)
        const halfBand = MAX_HALF_BAND * (counts[idx] / maxCount)
        const rand = stableRandom(p.movie_id)
        const y = (rand * 2 - 1) * halfBand

        return {
            movie_id: p.movie_id,
            title: p.title,
            score: p.score,
            y,
            vote_count: p.vote_count,
            isPolestar: positiveStars.has(p.movie_id) || negativeStars.has(p.movie_id),
        }
    })
}
