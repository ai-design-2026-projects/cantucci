/** Shared chart palette, margins, and formatters for the Eval Lab. */

export const CHART_COLORS = {
  primary: "#f59e0b",       // amber-400
  primaryMuted: "#fde68a",  // amber-200
  neutral: "#64748b",       // slate-500
  success: "#10b981",       // emerald-500
  personas: [
    "#f59e0b", // amber
    "#6366f1", // indigo
    "#10b981", // emerald
    "#f43f5e", // rose
    "#8b5cf6", // violet
  ],
  ciBand: "rgba(245, 158, 11, 0.15)",
  ciLine: "rgba(245, 158, 11, 0.6)",
  grid: "rgba(100, 116, 139, 0.15)",
};

export const CHART_MARGINS = { top: 10, right: 20, left: 8, bottom: 8 };

export function fmtPercent(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

export function fmtUSD(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  return `$${v.toFixed(4)}`;
}

export function fmtNum(v: number | null | undefined, dp = 2): string {
  if (v == null || isNaN(v)) return "—";
  return v.toFixed(dp);
}

export function fmtScore(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  return `${v.toFixed(2)} / 5`;
}

export type MetricFormat = "percent" | "usd" | "count" | "score" | "number";

export function formatMetricValue(v: number, fmt: MetricFormat): string {
  switch (fmt) {
    case "percent": return fmtPercent(v);
    case "usd":     return fmtUSD(v);
    case "count":   return fmtNum(v, 1);
    case "score":   return fmtScore(v);
    default:        return fmtNum(v);
  }
}
