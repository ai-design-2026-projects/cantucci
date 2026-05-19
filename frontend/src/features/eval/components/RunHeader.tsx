import { Calendar, Cpu, Hash, Layers, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtPercent, fmtUSD, fmtNum } from "@/features/eval/charts/chartTheme";
import type { RunDetail } from "@/utils/types";

const STATUS_STYLES: Record<string, string> = {
  running: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  completed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  aborted: "bg-rose-500/15 text-rose-400 border-rose-500/30",
};

const CONDITION_STYLES: Record<string, string> = {
  baseline: "bg-slate-500/15 text-slate-400",
  uncertainty: "bg-violet-500/15 text-violet-400",
  random: "bg-cyan-500/15 text-cyan-400",
  boundary: "bg-orange-500/15 text-orange-400",
  popularity: "bg-pink-500/15 text-pink-400",
  component_test: "bg-teal-500/15 text-teal-400",
  human: "bg-blue-500/15 text-blue-400",
};

function formatDateRange(from: string | null, to: string | null): string {
  const fmt = (d: string | null) =>
    d ? new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—";
  return `${fmt(from)} → ${fmt(to)}`;
}

interface KpiCardProps {
  label: string;
  value: string;
  sub?: string;
}

function KpiCard({ label, value, sub }: KpiCardProps) {
  return (
    <Card className="flex-1 min-w-[120px]">
      <CardContent className="p-4">
        <p className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider mb-1">{label}</p>
        <p className="text-2xl font-display font-semibold text-foreground tabular-nums leading-none">{value}</p>
        {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}

interface RunHeaderProps {
  run: RunDetail;
  onViewConfig: () => void;
}

/**
 * Top strip showing run metadata badges, date range, and 4 KPI summary cards.
 */
export function RunHeader({ run, onViewConfig }: RunHeaderProps) {
  const agg = run.aggregate;
  return (
    <div className="space-y-4 p-5 border-b border-border">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="space-y-1.5">
          <h2 className="font-display text-xl font-semibold text-foreground">{run.name}</h2>
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[run.status] ?? ""}`}
            >
              {run.status}
            </span>
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${CONDITION_STYLES[run.condition] ?? "bg-muted text-muted-foreground"}`}
            >
              {run.condition}
            </span>
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Calendar className="h-3 w-3" />
              {formatDateRange(run.started_at, run.ended_at)}
            </span>
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Layers className="h-3 w-3" />
              {run.n_sessions} sessions
            </span>
            <span className="flex items-center gap-1 text-xs text-muted-foreground font-mono">
              <Cpu className="h-3 w-3" />
              {run.model_version}
            </span>
            <span className="flex items-center gap-1 text-xs text-muted-foreground font-mono">
              <Hash className="h-3 w-3" />
              {run.config_hash}
            </span>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={onViewConfig} className="gap-1.5 shrink-0">
          <Settings2 className="h-3.5 w-3.5" />
          View Config
        </Button>
      </div>

      <div className="flex gap-3 flex-wrap">
        <KpiCard
          label="Converged"
          value={fmtPercent(agg.converged_rate.value)}
          sub={`CI [${fmtPercent(agg.converged_rate.ci_lo)} – ${fmtPercent(agg.converged_rate.ci_hi)}]`}
        />
        <KpiCard
          label="Precision @K"
          value={fmtPercent(agg.precision_at_k.value)}
          sub={`n = ${agg.precision_at_k.n}`}
        />
        <KpiCard
          label="NDCG @K"
          value={fmtNum(agg.ndcg_at_k.value)}
          sub={`n = ${agg.ndcg_at_k.n}`}
        />
        <KpiCard
          label="Avg Cost"
          value={fmtUSD(agg.total_cost_usd.value)}
          sub="per session"
        />
      </div>
    </div>
  );
}

export function RunHeaderSkeleton() {
  return (
    <div className="p-5 border-b border-border space-y-4">
      <Skeleton className="h-6 w-48" />
      <div className="flex gap-2">
        {[80, 60, 100, 80].map((w, i) => <Skeleton key={i} className={`h-5 w-${w}`} />)}
      </div>
      <div className="flex gap-3">
        {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-20 flex-1 rounded-lg" />)}
      </div>
    </div>
  );
}
