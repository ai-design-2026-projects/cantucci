export interface BoxStats {
    min: number
    q1: number
    median: number
    q3: number
    max: number
    mean: number
    std: number
    n: number
    /** 95% confidence interval of the mean: [lower, upper] */
    ci95: [number, number]
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
    const ci95: [number, number] = [mean - 1.96 * sem, mean + 1.96 * sem]

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
