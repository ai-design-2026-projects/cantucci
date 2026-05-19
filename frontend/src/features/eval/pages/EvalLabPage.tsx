import { useSearchParams } from "react-router-dom";
import { FlaskConical } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { RunsSidebar } from "@/features/eval/components/RunsSidebar";
import { RunHeader, RunHeaderSkeleton } from "@/features/eval/components/RunHeader";
import { AggregateSection } from "@/features/eval/components/AggregateSection";
import { PerPersonaSection } from "@/features/eval/components/PerPersonaSection";
import { SessionDrilldownTable } from "@/features/eval/components/SessionDrilldownTable";
import { ConfigInspectorSheet } from "@/features/eval/components/ConfigInspectorSheet";
import {
  useRunDetail,
  useRunAggregateByPersona,
  useRunSessions,
} from "@/features/eval/hooks/useEvalQueries";
import { useState } from "react";
import type { RunDetail } from "@/utils/types";

const SIDEBAR_WIDTH = 280;

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center p-12 gap-4">
      <FlaskConical className="h-12 w-12 text-amber-400/40" />
      <div>
        <p className="text-lg font-display font-semibold text-foreground">Select a run</p>
        <p className="text-sm text-muted-foreground mt-1">
          Pick an eval run from the sidebar to inspect its metrics and session details.
        </p>
      </div>
    </div>
  );
}

function RunDetail({ runId }: { runId: string }) {
  const { data: run, isLoading: loadingDetail } = useRunDetail(runId);
  const { data: byPersona = {}, isLoading: loadingPersona } = useRunAggregateByPersona(runId);
  const { data: sessions = [], isLoading: loadingSessions } = useRunSessions(runId);
  const [configOpen, setConfigOpen] = useState(false);

  if (loadingDetail) {
    return (
      <div className="flex-1 overflow-auto">
        <RunHeaderSkeleton />
        <div className="p-5 space-y-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-32 w-full rounded-lg" />)}
        </div>
      </div>
    );
  }

  if (!run) return null;

  const hasPersonas = Object.keys(byPersona).length > 0;

  return (
    <>
      <ScrollArea className="flex-1">
        <div className="min-h-full">
          <RunHeader run={run} onViewConfig={() => setConfigOpen(true)} />
          <Separator />
          <AggregateSection bundle={run.aggregate} />
          {hasPersonas && !loadingPersona && (
            <>
              <Separator />
              <PerPersonaSection byPersona={byPersona} sessions={sessions} />
            </>
          )}
          {!loadingSessions && sessions.length > 0 && (
            <>
              <Separator />
              <SessionDrilldownTable sessions={sessions} />
            </>
          )}
        </div>
      </ScrollArea>

      <ConfigInspectorSheet
        run={run}
        open={configOpen}
        onOpenChange={setConfigOpen}
      />
    </>
  );
}

/**
 * Eval Lab — the admin-only evaluation inspection page.
 *
 * Three-pane layout:
 *  - Left rail: runs list with filters (always visible, fixed width).
 *  - Centre: run detail (header KPIs, charts, drilldown table).
 *  - Right: slides-in Sheet for config or session detail.
 *
 * Selected run is stored in ?run= query param so the page is bookmark-safe.
 */
export function EvalLabPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedRunId = searchParams.get("run");

  function handleSelect(id: string) {
    setSearchParams({ run: id }, { replace: true });
  }

  return (
    <div
      className="flex h-[calc(100dvh-52px)] overflow-hidden"
      style={{ paddingTop: 0 }}
    >
      {/* Left sidebar */}
      <aside
        className="shrink-0 border-r border-border bg-background/95 overflow-hidden"
        style={{ width: SIDEBAR_WIDTH }}
      >
        <RunsSidebar selectedRunId={selectedRunId} onSelect={handleSelect} />
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {selectedRunId ? (
          <RunDetail runId={selectedRunId} />
        ) : (
          <EmptyState />
        )}
      </div>
    </div>
  );
}
