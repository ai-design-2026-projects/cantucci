export interface BoxStats {
    min: number
    q1: number
    median: number
    q3: number
    max: number
    mean: number
    std: number
    n: number
    /** Two-sided 95% t-based CI of the mean: [lower, upper]. Zero-width when n < 2. */
    ci95: [number, number]
}

/**
 * Two-sided 95% t-critical value for the given degrees of freedom.
 * Uses a lookup table for df 1–30; falls back to 1.96 (z∞) for df ≥ 31.
 */
function tCrit(df: number): number {
    const TABLE: Record<number, number> = {
        1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
        6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
        21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
        26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
    }
    return TABLE[df] ?? 1.96
}

/** Compute descriptive stats and 95% CI of the mean from a numeric array. */
export function computeBoxStats(values: number[]): BoxStats | null {
    const clean = values.filter((v) => v != null && isFinite(v))
    if (clean.length === 0) return null

    const sorted = [...clean].sort((a, b) => a - b)
    const n = sorted.length
    const mean = sorted.reduce((s, v) => s + v, 0) / n
    const variance = sorted.reduce((s, v) => s + (v - mean) ** 2, 0) / (n > 1 ? n - 1 : 1)
    const std = Math.sqrt(variance)
    const sem = std / Math.sqrt(n)
    const ci95: [number, number] = sem === 0
        ? [mean, mean]
        : [mean - tCrit(n - 1) * sem, mean + tCrit(n - 1) * sem]

    return {
        min: sorted[0],
        q1: quantile(sorted, 0.25),
        median: quantile(sorted, 0.5),
        q3: quantile(sorted, 0.75),
        max: sorted[n - 1],
        mean,
        std,
        n,
        ci95,
    }
}

function quantile(sorted: number[], p: number): number {
    const idx = p * (sorted.length - 1)
    const lo = Math.floor(idx)
    const hi = Math.ceil(idx)
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo)
}

/** Bin an array of values into `bins` equal-width histogram buckets. */
export function histogram(values: number[], bins = 10): Array<{ x0: number; x1: number; count: number }> {
    const clean = values.filter((v) => v != null && isFinite(v))
    if (clean.length === 0) return []
    const min = Math.min(...clean)
    const max = Math.max(...clean)
    if (min === max) {
        return [{ x0: min - 0.5, x1: max + 0.5, count: clean.length }]
    }
    const width = (max - min) / bins
    const buckets = Array.from({ length: bins }, (_, i) => ({
        x0: min + i * width,
        x1: min + (i + 1) * width,
        count: 0,
    }))
    for (const v of clean) {
        const i = Math.min(Math.floor((v - min) / width), bins - 1)
        buckets[i].count++
    }
    return buckets
}

/** Format a number for display — 3 significant figures, no trailing zeros. */
export function fmt(v: number | null | undefined): string {
    if (v == null || !isFinite(v)) return '—'
    if (Math.abs(v) >= 1000) return v.toFixed(0)
    if (Math.abs(v) >= 100) return v.toFixed(1)
    if (Math.abs(v) >= 10) return v.toFixed(2)
    return v.toFixed(3)
}
