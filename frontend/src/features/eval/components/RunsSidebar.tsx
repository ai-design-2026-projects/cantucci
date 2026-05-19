import { useState } from "react";
import { Activity, CheckCircle2, Clock, XCircle } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useRuns } from "@/features/eval/hooks/useEvalQueries";
import { RunFilters } from "./RunFilters";
import { cn } from "@/lib/utils";
import type { RunFilters as RunFiltersState, RunStatus, RunSummary } from "@/utils/types";

const STATUS_ICON: Record<RunStatus, React.ReactNode> = {
  running: <Activity className="h-3 w-3 text-amber-400 animate-pulse" />,
  completed: <CheckCircle2 className="h-3 w-3 text-emerald-400" />,
  aborted: <XCircle className="h-3 w-3 text-rose-400" />,
};

const CONDITION_COLORS: Record<string, string> = {
  baseline: "bg-slate-500/20 text-slate-400",
  uncertainty: "bg-violet-500/20 text-violet-400",
  random: "bg-cyan-500/20 text-cyan-400",
  boundary: "bg-orange-500/20 text-orange-400",
  popularity: "bg-pink-500/20 text-pink-400",
  component_test: "bg-teal-500/20 text-teal-400",
  human: "bg-blue-500/20 text-blue-400",
};

function formatDate(dt: string | null) {
  if (!dt) return null;
  return new Date(dt).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "2-digit" });
}

interface RunListItemProps {
  run: RunSummary;
  isActive: boolean;
  onClick: () => void;
}

function RunListItem({ run, isActive, onClick }: RunListItemProps) {
  return (
    <button
      type="button"
      className={cn(
        "w-full text-left px-3 py-2.5 rounded-md cursor-pointer text-sm transition-colors space-y-1",
        isActive
          ? "bg-amber-500/15 text-foreground border border-amber-500/30"
          : "text-muted-foreground hover:bg-muted hover:text-foreground border border-transparent"
      )}
      onClick={onClick}
    >
      <div className="flex items-center gap-1.5">
        {STATUS_ICON[run.status]}
        <span className="flex-1 truncate font-medium text-foreground text-xs">{run.name}</span>
      </div>
      <div className="flex items-center gap-1.5 flex-wrap">
        <span
          className={cn(
            "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium",
            CONDITION_COLORS[run.condition] ?? "bg-muted text-muted-foreground"
          )}
        >
          {run.condition}
        </span>
        <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
          <Clock className="h-2.5 w-2.5" />
          {formatDate(run.started_at) ?? "—"}
        </span>
        <span className="text-[10px] text-muted-foreground ml-auto">{run.n_sessions}s</span>
      </div>
    </button>
  );
}

function applyFilters(runs: RunSummary[], f: RunFiltersState): RunSummary[] {
  return runs.filter((r) => {
    if (f.name && !r.name.toLowerCase().includes(f.name.toLowerCase())) return false;
    if (f.condition && r.condition !== f.condition) return false;
    if (f.status && r.status !== f.status) return false;
    if (f.dateFrom && r.started_at && r.started_at < f.dateFrom) return false;
    if (f.dateTo && r.started_at && r.started_at > f.dateTo + "T23:59:59") return false;
    return true;
  });
}

interface RunsSidebarProps {
  selectedRunId: string | null;
  onSelect: (id: string) => void;
}

/**
 * Left-rail panel listing eval runs with filter controls.
 * Mirrors the SessionSidebar pattern without create/delete actions.
 */
export function RunsSidebar({ selectedRunId, onSelect }: RunsSidebarProps) {
  const [filters, setFilters] = useState<RunFiltersState>({
    name: "",
    condition: "",
    status: "",
    dateFrom: "",
    dateTo: "",
  });

  const { data: runs = [], isLoading } = useRuns();
  const filtered = applyFilters(runs, filters);

  return (
    <div className="flex flex-col h-full py-2">
      <div className="px-3 pb-2">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
          Eval Runs
        </p>
        <RunFilters filters={filters} onChange={setFilters} />
      </div>

      <ScrollArea className="flex-1 px-2">
        {isLoading ? (
          <div className="space-y-1.5 px-1">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-14 w-full rounded-md" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <p className="px-1 py-3 text-xs text-muted-foreground text-center">
            {runs.length === 0 ? "No eval runs yet." : "No runs match filters."}
          </p>
        ) : (
          <div className="space-y-0.5">
            {filtered.map((r) => (
              <RunListItem
                key={r.id}
                run={r}
                isActive={r.id === selectedRunId}
                onClick={() => onSelect(r.id)}
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
