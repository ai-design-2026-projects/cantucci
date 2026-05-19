import { useState } from "react";
import { ArrowUpDown, CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { SessionDetailSheet } from "./SessionDetailSheet";
import { fmtNum, fmtPercent, fmtUSD, fmtScore } from "@/features/eval/charts/chartTheme";
import { cn } from "@/lib/utils";
import type { EvalSessionRow } from "@/utils/types";

type SortKey = keyof EvalSessionRow;

const PAGE_SIZE = 15;

function BoolCell({ v }: { v: boolean }) {
  return v
    ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 mx-auto" />
    : <XCircle className="h-3.5 w-3.5 text-rose-400 mx-auto" />;
}

const COLS: { key: SortKey; label: string; render: (r: EvalSessionRow) => React.ReactNode; align?: string }[] = [
  { key: "persona_id",             label: "Persona",        render: (r) => <span className="font-mono text-[10px]">{r.persona_id ?? "—"}</span> },
  { key: "ground_truth_id",        label: "GT",             render: (r) => <span className="font-mono text-[10px]">{r.ground_truth_id ?? "—"}</span> },
  { key: "converged",              label: "Conv.",          render: (r) => <BoolCell v={r.converged} />,           align: "text-center" },
  { key: "turns_to_convergence",   label: "Turns",          render: (r) => r.turns_to_convergence ?? "—",         align: "text-center tabular-nums" },
  { key: "precision_at_k",         label: "P@K",            render: (r) => r.precision_at_k != null ? fmtPercent(r.precision_at_k) : "—", align: "text-right tabular-nums" },
  { key: "recall_at_k",            label: "R@K",            render: (r) => r.recall_at_k != null ? fmtPercent(r.recall_at_k) : "—",    align: "text-right tabular-nums" },
  { key: "ndcg_at_k",              label: "NDCG",           render: (r) => r.ndcg_at_k != null ? fmtNum(r.ndcg_at_k) : "—",           align: "text-right tabular-nums" },
  { key: "avg_cognitive_load",     label: "Cog.",           render: (r) => r.avg_cognitive_load != null ? fmtNum(r.avg_cognitive_load) : "—", align: "text-right tabular-nums" },
  { key: "total_cost_usd",         label: "Cost",           render: (r) => fmtUSD(r.total_cost_usd),              align: "text-right tabular-nums" },
  { key: "judge_clustering_coherence", label: "Coh.",       render: (r) => r.judge_clustering_coherence != null ? fmtScore(r.judge_clustering_coherence) : "—", align: "text-right tabular-nums" },
  { key: "judge_question_quality", label: "Q.Q.",           render: (r) => r.judge_question_quality != null ? fmtScore(r.judge_question_quality) : "—",    align: "text-right tabular-nums" },
  { key: "judge_profile_fidelity", label: "P.F.",           render: (r) => r.judge_profile_fidelity != null ? fmtScore(r.judge_profile_fidelity) : "—",   align: "text-right tabular-nums" },
];

interface SessionDrilldownTableProps {
  sessions: EvalSessionRow[];
}

/**
 * Sortable, paginated table of per-session eval metrics.
 * Clicking a row opens a SessionDetailSheet.
 */
export function SessionDrilldownTable({ sessions }: SessionDrilldownTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("precision_at_k");
  const [sortAsc, setSortAsc] = useState(false);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<EvalSessionRow | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortAsc((p) => !p);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
    setPage(0);
  }

  const sorted = [...sessions].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortAsc ? cmp : -cmp;
  });

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);
  const paged = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <>
      <div className="px-5 pb-5">
        <h3 className="text-sm font-semibold text-foreground mb-3">Session Drilldown</h3>
        <Card>
          <CardContent className="p-0 overflow-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  {COLS.map((col) => (
                    <th
                      key={col.key}
                      className={cn(
                        "px-3 py-2.5 font-medium text-muted-foreground whitespace-nowrap cursor-pointer hover:text-foreground select-none",
                        col.align ?? "text-left"
                      )}
                      onClick={() => toggleSort(col.key)}
                    >
                      <span className="inline-flex items-center gap-0.5">
                        {col.label}
                        {sortKey === col.key && (
                          <ArrowUpDown className="h-2.5 w-2.5 opacity-60" />
                        )}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {paged.length === 0 ? (
                  <tr>
                    <td colSpan={COLS.length} className="px-3 py-8 text-center text-muted-foreground">
                      No sessions.
                    </td>
                  </tr>
                ) : (
                  paged.map((row) => (
                    <tr
                      key={row.session_id}
                      className="border-b border-border/50 hover:bg-muted/30 cursor-pointer transition-colors"
                      onClick={() => {
                        setSelected(row);
                        setSheetOpen(true);
                      }}
                    >
                      {COLS.map((col) => (
                        <td key={col.key} className={cn("px-3 py-2", col.align ?? "text-left")}>
                          {col.render(row)}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </CardContent>
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-2 border-t border-border text-xs text-muted-foreground">
              <span>{sorted.length} sessions</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                  className="px-2 py-0.5 rounded hover:bg-muted disabled:opacity-40"
                >
                  ←
                </button>
                <span>{page + 1} / {totalPages}</span>
                <button
                  type="button"
                  disabled={page === totalPages - 1}
                  onClick={() => setPage((p) => p + 1)}
                  className="px-2 py-0.5 rounded hover:bg-muted disabled:opacity-40"
                >
                  →
                </button>
              </div>
            </div>
          )}
        </Card>
      </div>

      <SessionDetailSheet
        session={selected}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </>
  );
}
