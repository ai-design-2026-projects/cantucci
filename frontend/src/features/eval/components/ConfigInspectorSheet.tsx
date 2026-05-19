import { useState } from "react";
import { Check, Copy, Settings2 } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import type { RunDetail } from "@/utils/types";

function renderValue(v: unknown): React.ReactNode {
  if (v === null || v === undefined) {
    return <span className="text-muted-foreground italic">null</span>;
  }
  if (typeof v === "boolean") {
    return (
      <span
        className={cn(
          "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold",
          v ? "bg-emerald-500/15 text-emerald-400" : "bg-rose-500/15 text-rose-400"
        )}
      >
        {v ? "ON" : "OFF"}
      </span>
    );
  }
  if (typeof v === "number") {
    return <span className="font-mono tabular-nums text-amber-400">{v}</span>;
  }
  if (typeof v === "string") {
    return <span className="font-mono text-sky-300">{v}</span>;
  }
  if (Array.isArray(v)) {
    return (
      <div className="flex flex-wrap gap-1">
        {(v as unknown[]).map((item, i) => (
          <span key={i} className="inline-flex items-center rounded px-1.5 py-0.5 bg-muted text-[10px] font-mono text-foreground">
            {String(item)}
          </span>
        ))}
      </div>
    );
  }
  return <span className="font-mono text-xs text-muted-foreground">{JSON.stringify(v)}</span>;
}

function cn(...classes: (string | undefined | false)[]): string {
  return classes.filter(Boolean).join(" ");
}

function SectionCard({ title, data }: { title: string; data: Record<string, unknown> }) {
  const [copied, setCopied] = useState(false);

  function copySection() {
    void navigator.clipboard.writeText(JSON.stringify(data, null, 2)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className="rounded-lg border border-border bg-muted/20 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 bg-muted/40 border-b border-border">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {title}
        </span>
        <button
          type="button"
          onClick={copySection}
          className="text-muted-foreground hover:text-foreground transition-colors"
          title="Copy section"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>
      <div className="divide-y divide-border">
        {Object.entries(data).map(([key, val]) => (
          typeof val !== "object" || val === null || Array.isArray(val) ? (
            <div key={key} className="flex items-start justify-between gap-3 px-4 py-2.5">
              <span className="text-xs text-muted-foreground shrink-0 min-w-[120px]">{key}</span>
              <div className="text-xs text-right">{renderValue(val)}</div>
            </div>
          ) : null
        ))}
      </div>
    </div>
  );
}

interface ConfigInspectorSheetProps {
  run: RunDetail | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Right-side Sheet that renders run config_snapshot as human-friendly section cards.
 * Each top-level key in the snapshot becomes a card with formatted key-value rows.
 * A "Show raw" toggle reveals the full JSON for copy-paste.
 */
export function ConfigInspectorSheet({ run, open, onOpenChange }: ConfigInspectorSheetProps) {
  const [showRaw, setShowRaw] = useState(false);
  const [copiedRaw, setCopiedRaw] = useState(false);

  const snapshot = run?.config_snapshot as Record<string, unknown> | undefined;

  function copyRaw() {
    if (!snapshot) return;
    void navigator.clipboard.writeText(JSON.stringify(snapshot, null, 2)).then(() => {
      setCopiedRaw(true);
      setTimeout(() => setCopiedRaw(false), 1500);
    });
  }

  const sections = snapshot
    ? Object.entries(snapshot).filter(([, v]) => typeof v === "object" && v !== null && !Array.isArray(v))
    : [];
  const topLevel = snapshot
    ? Object.fromEntries(
        Object.entries(snapshot).filter(([, v]) => typeof v !== "object" || v === null || Array.isArray(v))
      )
    : {};

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-md flex flex-col p-0 gap-0">
        <SheetHeader className="px-5 py-4 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <Settings2 className="h-4 w-4 text-amber-400" />
            <SheetTitle className="text-base">Run Config</SheetTitle>
          </div>
          {run && (
            <div className="flex flex-wrap gap-1.5 mt-1">
              <span className="text-xs text-muted-foreground font-mono">{run.config_hash}</span>
              <span className="text-xs text-muted-foreground">· {run.model_version}</span>
              <span className="text-xs text-muted-foreground">· seed {run.seed}</span>
            </div>
          )}
        </SheetHeader>

        <ScrollArea className="flex-1 px-5 py-4">
          {!snapshot ? (
            <p className="text-sm text-muted-foreground text-center py-8">No config available.</p>
          ) : (
            <div className="space-y-3">
              {Object.keys(topLevel).length > 0 && (
                <SectionCard title="General" data={topLevel} />
              )}
              {sections.map(([key, val]) => (
                <SectionCard key={key} title={key} data={val as Record<string, unknown>} />
              ))}

              <Separator />

              <div className="flex items-center justify-between">
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                  onClick={() => setShowRaw((p) => !p)}
                >
                  {showRaw ? "Hide raw JSON" : "Show raw JSON"}
                </button>
                {showRaw && (
                  <button type="button" onClick={copyRaw} className="text-muted-foreground hover:text-foreground transition-colors">
                    {copiedRaw ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                  </button>
                )}
              </div>

              {showRaw && (
                <pre className="text-[10px] font-mono bg-muted/40 border border-border rounded-lg p-3 overflow-auto text-foreground leading-relaxed">
                  {JSON.stringify(snapshot, null, 2)}
                </pre>
              )}
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
