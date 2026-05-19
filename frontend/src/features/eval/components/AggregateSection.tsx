import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MetricBarChart, metricCItoEntry } from "@/features/eval/charts/MetricBarChart";
import { CHART_COLORS } from "@/features/eval/charts/chartTheme";
import type { MetricBundle, MetricCI } from "@/utils/types";

interface ChartCardProps {
  title: string;
  ci: MetricCI;
  format: "percent" | "usd" | "count" | "score" | "number";
  domain?: [number | "auto", number | "auto"];
  color?: string;
}

function MetricChartCard({ title, ci, format, domain, color }: ChartCardProps) {
  const isEmpty = ci.n === 0 || isNaN(ci.value);
  return (
    <Card>
      <CardHeader className="pb-2 px-4 pt-4">
        <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-2 pb-3">
        {isEmpty ? (
          <div className="h-[200px] flex items-center justify-center text-xs text-muted-foreground">
            Insufficient data
          </div>
        ) : (
          <MetricBarChart
            entries={[metricCItoEntry(ci, "Overall", color)]}
            format={format}
            domain={domain}
          />
        )}
      </CardContent>
    </Card>
  );
}

interface AggregateSectionProps {
  bundle: MetricBundle;
}

/**
 * Three sub-sections: Objective metrics, Behavioral metrics, and Judge dimensions.
 * Each metric gets its own card with a single bar + error-bar CI.
 */
export function AggregateSection({ bundle }: AggregateSectionProps) {
  return (
    <div className="space-y-6 px-5 py-5">
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-3">Objective Metrics</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <MetricChartCard title="Precision @K" ci={bundle.precision_at_k} format="percent" domain={[0, 1]} />
          <MetricChartCard title="Recall @K" ci={bundle.recall_at_k} format="percent" domain={[0, 1]} />
          <MetricChartCard title="NDCG @K" ci={bundle.ndcg_at_k} format="number" domain={[0, 1]} />
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-foreground mb-3">Behavioral Metrics</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
          <MetricChartCard title="Converged" ci={bundle.converged_rate} format="percent" domain={[0, 1]} color={CHART_COLORS.success} />
          <MetricChartCard title="Explicit Acceptance" ci={bundle.explicit_acceptance_rate} format="percent" domain={[0, 1]} color={CHART_COLORS.success} />
          <MetricChartCard title="Turns to Converge" ci={bundle.turns_to_convergence} format="count" />
          <MetricChartCard title="Cognitive Load" ci={bundle.avg_cognitive_load} format="number" domain={[0, 1]} />
          <MetricChartCard title="Drift Events" ci={bundle.drift_events} format="count" />
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-foreground mb-3">Judge Dimensions</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <MetricChartCard title="Clustering Coherence" ci={bundle.judge_clustering_coherence} format="score" domain={[0, 5]} color="#8b5cf6" />
          <MetricChartCard title="Question Quality" ci={bundle.judge_question_quality} format="score" domain={[0, 5]} color="#8b5cf6" />
          <MetricChartCard title="Profile Fidelity" ci={bundle.judge_profile_fidelity} format="score" domain={[0, 5]} color="#8b5cf6" />
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-foreground mb-3">Cost</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <MetricChartCard title="Total Cost / Session" ci={bundle.total_cost_usd} format="usd" color={CHART_COLORS.neutral} />
        </div>
      </div>
    </div>
  );
}
