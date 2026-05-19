import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ErrorBar,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS, CHART_MARGINS, type MetricFormat, formatMetricValue } from "./chartTheme";
import type { MetricCI } from "@/utils/types";

interface BarEntry {
  label: string;
  value: number;
  ciLo: number;
  ciHi: number;
  n: number;
  color?: string;
}

interface MetricBarChartProps {
  /** One entry per bar (single metric overall, or one per persona). */
  entries: BarEntry[];
  format: MetricFormat;
  /** Y-axis domain override (e.g. [0, 1] for proportions, [0, 5] for judge scores). */
  domain?: [number | "auto", number | "auto"];
}

/**
 * Bar chart with per-bar 95% CI error bars. Tooltip shows value, CI bounds, and n.
 */
export function MetricBarChart({ entries, format, domain = [0, "auto"] }: MetricBarChartProps) {
  const data = entries.map((e) => ({
    ...e,
    ciRange: [e.value - e.ciLo, e.ciHi - e.value] as [number, number],
  }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={CHART_MARGINS} barCategoryGap="35%">
        <CartesianGrid vertical={false} stroke={CHART_COLORS.grid} />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v) => formatMetricValue(v, format)}
          domain={domain}
          width={54}
        />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as BarEntry;
            return (
              <div className="rounded-md border border-border bg-card px-3 py-2 text-xs shadow-lg space-y-0.5">
                <p className="font-medium text-foreground">{d.label}</p>
                <p className="text-foreground">{formatMetricValue(d.value, format)}</p>
                <p className="text-muted-foreground">
                  95% CI [{formatMetricValue(d.ciLo, format)} – {formatMetricValue(d.ciHi, format)}]
                </p>
                <p className="text-muted-foreground">n = {d.n}</p>
              </div>
            );
          }}
        />
        <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={60} isAnimationActive={false}>
          {data.map((entry, idx) => (
            <Cell key={idx} fill={entry.color ?? CHART_COLORS.primary} />
          ))}
          <ErrorBar
            dataKey="ciRange"
            width={4}
            strokeWidth={2}
            stroke={CHART_COLORS.ciLine}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Build a single-entry BarEntry from a MetricCI. */
export function metricCItoEntry(ci: MetricCI, label: string, color?: string): BarEntry {
  return { label, value: ci.value, ciLo: ci.ci_lo, ciHi: ci.ci_hi, n: ci.n, color };
}
