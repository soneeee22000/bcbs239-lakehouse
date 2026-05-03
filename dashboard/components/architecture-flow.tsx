import { ArrowRight, Database } from "lucide-react";

const STAGES = [
  {
    name: "Synthetic CSV",
    detail: "data/synthetic/*.csv",
    note: "deterministic seed=42",
  },
  {
    name: "Bronze Delta",
    detail: "raw landings, STRING cols",
    note: "_source_file + _ingest_ts",
  },
  {
    name: "Silver Delta",
    detail: "typed casts + dedup",
    note: "latest-by silver_loaded_at",
  },
  {
    name: "Gold Delta",
    detail: "fact_rwa_aggregation + fact_dq_scorecard",
    note: "BCBS 239 dimensions",
  },
] as const;

export function ArchitectureFlow() {
  return (
    <div className="flex flex-col sm:flex-row items-stretch gap-3 sm:items-center">
      {STAGES.map((stage, i) => (
        <div key={stage.name} className="flex items-center gap-3 flex-1">
          <div className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-muted)]/40 p-3">
            <div className="flex items-center gap-2">
              <Database
                size={14}
                aria-hidden="true"
                className="text-[var(--color-primary)] shrink-0"
              />
              <p className="text-sm font-semibold">{stage.name}</p>
            </div>
            <p className="mt-1 text-xs font-mono text-[var(--color-muted-foreground)]">
              {stage.detail}
            </p>
            <p className="mt-1 text-xs text-[var(--color-muted-foreground)]">
              {stage.note}
            </p>
          </div>
          {i < STAGES.length - 1 ? (
            <ArrowRight
              size={20}
              aria-hidden="true"
              className="rotate-90 sm:rotate-0 text-[var(--color-muted-foreground)] shrink-0"
            />
          ) : null}
        </div>
      ))}
    </div>
  );
}
