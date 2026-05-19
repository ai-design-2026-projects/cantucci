import { LayoutGrid } from "lucide-react";
import { motion, LayoutGroup } from "framer-motion";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Mascot } from "@/components/mascot/Mascot";
import { ClusterCard } from "./ClusterCard";
import { useClusterSnapshotStore } from "@/store/clusterSnapshotStore";

/**
 * Right-side slide-in panel showing the live cluster snapshot.
 *
 * Self-contained: manages its own open state. Trigger button renders in the
 * header via the parent (SessionHeader imports and renders this component).
 *
 * Clusters animate in and reorder via framer-motion LayoutGroup when the
 * backend emits a new snapshot mid-turn.
 */
export function ClusterSnapshotSheet() {
  const { clusters, isRefining, open, setOpen } = useClusterSnapshotStore();
  const count = clusters.length;

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen(true)}
        className="gap-1.5"
        aria-label="Open clusters panel"
      >
        <LayoutGrid className="h-4 w-4" />
        <span className="hidden sm:inline">Clusters</span>
        {count > 0 && (
          <Badge variant="secondary" className="h-4 min-w-[1rem] px-1 text-[0.625rem] leading-none">
            {count}
          </Badge>
        )}
      </Button>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="w-full sm:max-w-xl flex flex-col p-0">
          <SheetHeader className="px-5 pt-5 pb-3 border-b border-border">
            <SheetTitle>Clusters</SheetTitle>
            <SheetDescription>
              {isRefining
                ? "Refining based on your feedback…"
                : count === 0
                ? "No clusters yet"
                : `${count} cluster${count !== 1 ? "s" : ""} discovered so far`}
            </SheetDescription>
          </SheetHeader>

          <ScrollArea className="flex-1 px-5 py-4">
            {count === 0 ? (
              <EmptyState />
            ) : (
              <LayoutGroup>
                <div className="flex flex-col gap-3">
                  {clusters.map((cluster) => (
                    <motion.div
                      key={cluster.id}
                      layout
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      transition={{ duration: 0.25 }}
                      className="min-w-0"
                    >
                      <ClusterCard cluster={cluster} isRefining={isRefining} />
                    </motion.div>
                  ))}
                </div>
              </LayoutGroup>
            )}
          </ScrollArea>
        </SheetContent>
      </Sheet>
    </>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-16 px-4 text-center">
      <Mascot pose="idle" size={72} />
      <p className="text-sm text-muted-foreground leading-relaxed max-w-[220px]">
        We haven't seen enough yet — tell me what you're in the mood for.
      </p>
    </div>
  );
}
