import type { AxisPointDto } from '@/api/dto/concepts'

export interface DensityBucket {
    /** Center of the score bucket in [-1, 1]. */
    x: number
    /** Number of movies whose score falls in this bucket. */
    count: number
    /** Title of the movie whose score is closest to the bucket center (for tooltip). */
    title: string
    movie_id: number
}

/**
 * Partition scored movies into equal-width buckets across [-1, 1] and return one
 * entry per non-empty bucket.
 *
 * Each bucket emits a single representative movie (the one whose score is closest
 * to the bucket center) so the caller can render one dot per bucket without vertical
 * stacking.
 *
 * @param points - Scored movie points (any order).
 * @param bins   - Number of equal-width buckets across [-1, 1]. Defaults to 48.
 * @returns One DensityBucket per non-empty bucket, ordered by ascending x.
 */
export function computeDensity(points: AxisPointDto[], bins = 48): DensityBucket[] {
    if (points.length === 0) return []

    const bucketWidth = 2 / bins

    const buckets = new Map<
        number,
        { count: number; bestDist: number; title: string; movie_id: number }
    >()

    for (const p of points) {
        const idx = Math.min(Math.floor((p.score + 1) / bucketWidth), bins - 1)
        const center = -1 + (idx + 0.5) * bucketWidth
        const dist = Math.abs(p.score - center)

        const existing = buckets.get(idx)
        if (!existing) {
            buckets.set(idx, { count: 1, bestDist: dist, title: p.title, movie_id: p.movie_id })
        } else {
            existing.count++
            if (dist < existing.bestDist) {
                existing.bestDist = dist
                existing.title = p.title
                existing.movie_id = p.movie_id
            }
        }
    }

    return Array.from(buckets.entries())
        .sort(([a], [b]) => a - b)
        .map(([idx, { count, title, movie_id }]) => ({
            x: -1 + (idx + 0.5) * bucketWidth,
            count,
            title,
            movie_id,
        }))
}
