import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ErrorBar,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MetricScatter } from "@/features/eval/charts/MetricScatter";
import { MetricHistogram } from "@/features/eval/charts/MetricHistogram";
import {
  CHART_COLORS,
  CHART_MARGINS,
  type MetricFormat,
} from "@/features/eval/charts/chartTheme";
import type { EvalSessionRow, MetricBundle } from "@/utils/types";

type MetricKey = keyof MetricBundle;

const METRICS: { key: MetricKey; label: string; format: MetricFormat; domain?: [number | "auto", number | "auto"] }[] = [
  { key: "precision_at_k",            label: "Precision @K",         format: "percent",  domain: [0, 1] },
  { key: "recall_at_k",               label: "Recall @K",            format: "percent",  domain: [0, 1] },
  { key: "ndcg_at_k",                 label: "NDCG @K",              format: "number",   domain: [0, 1] },
  { key: "converged_rate",            label: "Converged Rate",       format: "percent",  domain: [0, 1] },
  { key: "turns_to_convergence",      label: "Turns to Converge",    format: "count"  },
  { key: "avg_cognitive_load",        label: "Cognitive Load",       format: "number",   domain: [0, 1] },
  { key: "total_cost_usd",            label: "Cost / Session",       format: "usd"    },
  { key: "judge_clustering_coherence", label: "Coherence (Judge)",   format: "score",    domain: [0, 5] },
  { key: "judge_question_quality",    label: "Question Quality",     format: "score",    domain: [0, 5] },
  { key: "judge_profile_fidelity",    label: "Profile Fidelity",     format: "score",    domain: [0, 5] },
];

function getSessionValues(sessions: EvalSessionRow[], personaId: string, key: MetricKey): number[] {
  const pid = personaId === "__none__" ? null : personaId;
  return sessions
    .filter((s) => s.persona_id === pid)
    .map((s) => {
      const map: Record<MetricKey, number | null> = {
        precision_at_k: s.precision_at_k,
        recall_at_k: s.recall_at_k,
        ndcg_at_k: s.ndcg_at_k,
        turns_to_convergence: s.turns_to_convergence,
        avg_cognitive_load: s.avg_cognitive_load,
        total_cost_usd: s.total_cost_usd,
        drift_events: s.drift_events,
        converged_rate: s.converged ? 1 : 0,
        explicit_acceptance_rate: s.explicit_acceptance ? 1 : 0,
        judge_clustering_coherence: s.judge_clustering_coherence,
        judge_question_quality: s.judge_question_quality,
        judge_profile_fidelity: s.judge_profile_fidelity,
      };
      return map[key];
    })
    .filter((v): v is number => v !== null);
}

interface PerPersonaSectionProps {
  byPersona: Record<string, MetricBundle>;
  sessions: EvalSessionRow[];
}

/**
 * Grouped comparison of metrics across personas plus scatter/histogram
 * drill-down for a user-selected metric.
 */
export function PerPersonaSection({ byPersona, sessions }: PerPersonaSectionProps) {
  const [selectedMetric, setSelectedMetric] = useState<MetricKey>("precision_at_k");

  const personas = Object.keys(byPersona);
  if (personas.length === 0) return null;

  const metricMeta = METRICS.find((m) => m.key === selectedMetric) ?? METRICS[0];

  // Build grouped-bar data: one row per metric, one bar per persona
  const groupedData = METRICS.map((m) => {
    const row: Record<string, number | string | [number, number]> = { metric: m.label };
    personas.forEach((p) => {
      const ci = byPersona[p][m.key];
      row[p] = ci.value;
      row[`${p}_ciRange`] = [ci.value - ci.ci_lo, ci.ci_hi - ci.value] as [number, number];
    });
    return row;
  });

  const selectedMeta = METRICS.find((m) => m.key === selectedMetric) ?? METRICS[0];

  return (
    <div className="px-5 pb-5 space-y-5">
      <h3 className="text-sm font-semibold text-foreground">Per-Persona Breakdown</h3>

      {/* Grouped bar chart */}
      <Card>
        <CardHeader className="pb-2 px-4 pt-4">
          <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            All Metrics by Persona
          </CardTitle>
        </CardHeader>
        <CardContent className="px-2 pb-3">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={groupedData} margin={CHART_MARGINS} barCategoryGap="30%">
              <CartesianGrid vertical={false} stroke={CHART_COLORS.grid} />
              <XAxis
                dataKey="metric"
                tick={{ fontSize: 10, fill: "#94a3b8" }}
                axisLine={false}
                tickLine={false}
                angle={-25}
                textAnchor="end"
                height={50}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#94a3b8" }}
                axisLine={false}
                tickLine={false}
                width={44}
              />
              <Legend iconType="square" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <div className="rounded-md border border-border bg-card px-3 py-2 text-xs shadow-lg space-y-0.5">
                      <p className="font-medium text-foreground mb-1">{label}</p>
                      {payload.map((p, i) => (
                        <p key={i} className="text-muted-foreground" style={{ color: p.color }}>
                          {p.name}: {typeof p.value === "number" ? p.value.toFixed(3) : p.value}
                        </p>
                      ))}
                    </div>
                  );
                }}
              />
              {personas.map((persona, idx) => (
                <Bar
                  key={persona}
                  dataKey={persona}
                  name={persona}
                  fill={CHART_COLORS.personas[idx % CHART_COLORS.personas.length]}
                  radius={[3, 3, 0, 0]}
                  maxBarSize={24}
                >
                  <ErrorBar
                    dataKey={`${persona}_ciRange`}
                    width={3}
                    strokeWidth={1.5}
                    stroke={CHART_COLORS.personas[idx % CHART_COLORS.personas.length]}
                    opacity={0.6}
                  />
                </Bar>
              ))}
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Metric selector + drill-down */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <p className="text-xs text-muted-foreground">Drill into:</p>
          <select
            value={selectedMetric}
            onChange={(e) => setSelectedMetric(e.target.value as MetricKey)}
            className="rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-amber-400"
          >
            {METRICS.map((m) => (
              <option key={m.key} value={m.key}>{m.label}</option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {personas.map((persona, idx) => {
            const ci = byPersona[persona][selectedMetric];
            const vals = getSessionValues(sessions, persona, selectedMetric);
            const color = CHART_COLORS.personas[idx % CHART_COLORS.personas.length];
            return (
              <div key={persona} className="space-y-2">
                <p className="text-xs font-medium" style={{ color }}>
                  {persona === "__none__" ? "No persona" : persona}
                </p>
                <Card>
                  <CardHeader className="pb-1 px-4 pt-3">
                    <CardTitle className="text-[11px] text-muted-foreground uppercase tracking-wider">
                      {selectedMeta.label} — Scatter
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="px-2 pb-3">
                    <MetricScatter
                      values={vals}
                      aggregate={ci}
                      format={metricMeta.format}
                      domain={metricMeta.domain}
                    />
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-1 px-4 pt-3">
                    <CardTitle className="text-[11px] text-muted-foreground uppercase tracking-wider">
                      {selectedMeta.label} — Distribution
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="px-2 pb-3">
                    <MetricHistogram values={vals} aggregate={ci} format={metricMeta.format} />
                  </CardContent>
                </Card>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
