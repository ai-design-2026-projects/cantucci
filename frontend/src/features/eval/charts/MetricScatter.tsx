import {
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS, CHART_MARGINS, type MetricFormat, formatMetricValue } from "./chartTheme";
import type { MetricCI } from "@/utils/types";

interface MetricScatterProps {
  /** Per-session values to scatter. */
  values: number[];
  aggregate: MetricCI;
  format: MetricFormat;
  domain?: [number | "auto", number | "auto"];
}

/**
 * Scatter chart of per-session values with a bootstrap-mean reference line
 * and a shaded 95% CI band.
 */
export function MetricScatter({ values, aggregate, format, domain = [0, "auto"] }: MetricScatterProps) {
  const data = values.map((v, i) => ({ x: i + 1, y: v }));
  const { value, ci_lo, ci_hi } = aggregate;

  return (
    <ResponsiveContainer width="100%" height={200}>
      <ScatterChart margin={CHART_MARGINS}>
        <CartesianGrid stroke={CHART_COLORS.grid} />
        <XAxis
          dataKey="x"
          name="Session"
          type="number"
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          axisLine={false}
          tickLine={false}
          label={{ value: "Session #", position: "insideBottomRight", offset: -4, fontSize: 11, fill: "#94a3b8" }}
        />
        <YAxis
          dataKey="y"
          name="Value"
          type="number"
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
            const pt = payload[0].payload as { x: number; y: number };
            return (
              <div className="rounded-md border border-border bg-card px-3 py-2 text-xs shadow-lg space-y-0.5">
                <p className="text-muted-foreground">Session #{pt.x}</p>
                <p className="font-medium text-foreground">{formatMetricValue(pt.y, format)}</p>
              </div>
            );
          }}
        />
        {!isNaN(ci_lo) && !isNaN(ci_hi) && (
          <ReferenceArea y1={ci_lo} y2={ci_hi} fill={CHART_COLORS.ciBand} ifOverflow="extendDomain" />
        )}
        {!isNaN(value) && (
          <ReferenceLine
            y={value}
            stroke={CHART_COLORS.primary}
            strokeWidth={2}
            strokeDasharray="4 3"
            label={{ value: formatMetricValue(value, format), position: "insideTopRight", fontSize: 10, fill: CHART_COLORS.primary }}
          />
        )}
        <Scatter data={data} fill={CHART_COLORS.neutral} opacity={0.75} r={4} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
