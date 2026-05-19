import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RunFilters as RunFiltersState } from "@/utils/types";

const CONDITIONS = ["baseline", "uncertainty", "random", "boundary", "popularity", "component_test", "human"];
const STATUSES = ["running", "completed", "aborted"];

interface RunFiltersProps {
  filters: RunFiltersState;
  onChange: (f: RunFiltersState) => void;
}

const selectCls = "w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-amber-400";
const inputCls = cn(selectCls, "pr-6");

/**
 * Filter controls for the eval runs sidebar.
 */
export function RunFilters({ filters, onChange }: RunFiltersProps) {
  const set = <K extends keyof RunFiltersState>(k: K, v: RunFiltersState[K]) =>
    onChange({ ...filters, [k]: v });

  const hasAny =
    filters.name || filters.condition || filters.status || filters.dateFrom || filters.dateTo;

  return (
    <div className="px-2 pb-2 space-y-1.5">
      <div className="relative">
        <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground pointer-events-none" />
        <input
          placeholder="Search runs…"
          value={filters.name}
          onChange={(e) => set("name", e.target.value)}
          className={cn(inputCls, "pl-6")}
        />
        {filters.name && (
          <button
            type="button"
            className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            onClick={() => set("name", "")}
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
      <select
        value={filters.condition}
        onChange={(e) => set("condition", e.target.value as RunFiltersState["condition"])}
        className={selectCls}
      >
        <option value="">All conditions</option>
        {CONDITIONS.map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>
      <select
        value={filters.status}
        onChange={(e) => set("status", e.target.value as RunFiltersState["status"])}
        className={selectCls}
      >
        <option value="">All statuses</option>
        {STATUSES.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
      <div className="flex gap-1">
        <input
          type="date"
          value={filters.dateFrom}
          onChange={(e) => set("dateFrom", e.target.value)}
          className={cn(selectCls, "flex-1")}
          title="From date"
        />
        <input
          type="date"
          value={filters.dateTo}
          onChange={(e) => set("dateTo", e.target.value)}
          className={cn(selectCls, "flex-1")}
          title="To date"
        />
      </div>
      {hasAny && (
        <button
          type="button"
          className="text-xs text-amber-600 hover:text-amber-500 transition-colors"
          onClick={() =>
            onChange({ name: "", condition: "", status: "", dateFrom: "", dateTo: "" })
          }
        >
          Clear filters
        </button>
      )}
    </div>
  );
}
