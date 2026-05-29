import type { AxisPointDto } from '@/api/dto/concepts'

export interface BeeswarmPoint {
    movie_id: number
    title: string
    score: number
    lane: number
}

/**
 * Assign non-overlapping vertical lanes to points on a 1-D axis.
 *
 * Points are sorted by score (ascending). For each point we greedily pick the
 * nearest-to-zero free lane whose last occupant is further than `collisionRadius`
 * away in the score dimension.
 *
 * @param points        - Scored movie points (any order).
 * @param collisionRadius - Minimum score-distance between two points in the same
 *                          lane. Defaults to 0.025 (about 1.25% of the [-1,1] range).
 * @returns Points augmented with a `lane` integer offset (0, ±1, ±2, …).
 */
export function computeBeeswarm(
    points: AxisPointDto[],
    collisionRadius = 0.025,
): BeeswarmPoint[] {
    const sorted = [...points].sort((a, b) => a.score - b.score)

    // lastInLane[lane] = score of the last point placed in that lane
    const lastInLane = new Map<number, number>()

    return sorted.map((p) => {
        let lane = 0
        let step = 0

        // Probe outward: 0, 1, -1, 2, -2, …
        while (true) {
            const last = lastInLane.get(lane)
            if (last === undefined || p.score - last >= collisionRadius) {
                break
            }
            step++
            lane = step % 2 === 1 ? Math.ceil(step / 2) : -Math.floor(step / 2)
        }

        lastInLane.set(lane, p.score)
        return { movie_id: p.movie_id, title: p.title, score: p.score, lane }
    })
}
