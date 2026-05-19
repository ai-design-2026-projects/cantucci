import { CheckCircle2, XCircle } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { fmtNum, fmtPercent, fmtUSD, fmtScore } from "@/features/eval/charts/chartTheme";
import type { EvalSessionRow } from "@/utils/types";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-2">
      <span className="text-xs text-muted-foreground shrink-0 min-w-[160px]">{label}</span>
      <span className="text-xs text-right text-foreground">{value}</span>
    </div>
  );
}

function BoolIcon({ v }: { v: boolean }) {
  return v
    ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 inline" />
    : <XCircle className="h-3.5 w-3.5 text-rose-400 inline" />;
}

interface SessionDetailSheetProps {
  session: EvalSessionRow | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Right-side Sheet displaying all fields for a single drilldown session row.
 */
export function SessionDetailSheet({ session: s, open, onOpenChange }: SessionDetailSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-sm flex flex-col p-0 gap-0">
        <SheetHeader className="px-5 py-4 border-b border-border shrink-0">
          <SheetTitle className="text-sm font-mono truncate">{s?.session_id ?? "Session"}</SheetTitle>
          {s && (
            <p className="text-xs text-muted-foreground font-mono">
              {s.persona_id ?? "—"} · {s.ground_truth_id ?? "—"}
            </p>
          )}
        </SheetHeader>
        <ScrollArea className="flex-1 px-5 py-3">
          {!s ? (
            <p className="text-sm text-muted-foreground py-8 text-center">No session selected.</p>
          ) : (
            <div className="divide-y divide-border">
              <Row label="Converged" value={<BoolIcon v={s.converged} />} />
              <Row label="Explicit acceptance" value={<BoolIcon v={s.explicit_acceptance} />} />
              <Row label="Turns to convergence" value={s.turns_to_convergence ?? "—"} />
              <Row label="Avg cognitive load" value={s.avg_cognitive_load != null ? fmtNum(s.avg_cognitive_load) : "—"} />
              <Row label="Total cost" value={fmtUSD(s.total_cost_usd)} />
              <Row label="Drift events" value={s.drift_events} />

              <Separator className="my-1" />

              <Row label="Precision @K" value={s.precision_at_k != null ? fmtPercent(s.precision_at_k) : "—"} />
              <Row label="Recall @K" value={s.recall_at_k != null ? fmtPercent(s.recall_at_k) : "—"} />
              <Row label="NDCG @K" value={s.ndcg_at_k != null ? fmtNum(s.ndcg_at_k) : "—"} />

              <Separator className="my-1" />

              <Row label="Judge: Clustering Coherence" value={s.judge_clustering_coherence != null ? fmtScore(s.judge_clustering_coherence) : "—"} />
              <Row label="Judge: Question Quality" value={s.judge_question_quality != null ? fmtScore(s.judge_question_quality) : "—"} />
              <Row label="Judge: Profile Fidelity" value={s.judge_profile_fidelity != null ? fmtScore(s.judge_profile_fidelity) : "—"} />
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
