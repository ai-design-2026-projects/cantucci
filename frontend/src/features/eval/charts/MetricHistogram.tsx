import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS, CHART_MARGINS, type MetricFormat, formatMetricValue } from "./chartTheme";
import type { MetricCI } from "@/utils/types";

interface HistBin {
  label: string;
  lo: number;
  hi: number;
  count: number;
}

function buildBins(values: number[], bins = 8): HistBin[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) {
    return [{ label: formatMetricValue(min, "number"), lo: min, hi: max, count: values.length }];
  }
  const step = (max - min) / bins;
  const result: HistBin[] = Array.from({ length: bins }, (_, i) => ({
    lo: min + i * step,
    hi: min + (i + 1) * step,
    label: formatMetricValue(min + i * step, "number"),
    count: 0,
  }));
  for (const v of values) {
    const idx = Math.min(Math.floor((v - min) / step), bins - 1);
    result[idx].count++;
  }
  return result;
}

interface MetricHistogramProps {
  values: number[];
  aggregate: MetricCI;
  format: MetricFormat;
}

/**
 * Histogram of per-session values with mean reference line and CI band overlay.
 */
export function MetricHistogram({ values, aggregate, format }: MetricHistogramProps) {
  const bins = buildBins(values);
  const { value, ci_lo, ci_hi } = aggregate;

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={bins} margin={CHART_MARGINS} barCategoryGap="5%">
        <CartesianGrid vertical={false} stroke={CHART_COLORS.grid} />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 10, fill: "#94a3b8" }}
          axisLine={false}
          tickLine={false}
          interval={1}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
          label={{ value: "Sessions", angle: -90, position: "insideLeft", fontSize: 10, fill: "#94a3b8", offset: 8 }}
        />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const b = payload[0].payload as HistBin;
            return (
              <div className="rounded-md border border-border bg-card px-3 py-2 text-xs shadow-lg space-y-0.5">
                <p className="text-muted-foreground">
                  [{formatMetricValue(b.lo, format)} – {formatMetricValue(b.hi, format)})
                </p>
                <p className="font-medium text-foreground">{b.count} sessions</p>
              </div>
            );
          }}
        />
        {!isNaN(ci_lo) && !isNaN(ci_hi) && (
          <ReferenceArea x1={formatMetricValue(ci_lo, "number")} x2={formatMetricValue(ci_hi, "number")} fill={CHART_COLORS.ciBand} ifOverflow="extendDomain" />
        )}
        {!isNaN(value) && (
          <ReferenceLine
            x={formatMetricValue(value, "number")}
            stroke={CHART_COLORS.primary}
            strokeWidth={2}
            strokeDasharray="4 3"
            label={{ value: formatMetricValue(value, format), position: "top", fontSize: 10, fill: CHART_COLORS.primary }}
          />
        )}
        <Bar dataKey="count" fill={CHART_COLORS.neutral} fillOpacity={0.75} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

// Re-export formatMetricValue so callers can use it without importing chartTheme directly
export { formatMetricValue };
