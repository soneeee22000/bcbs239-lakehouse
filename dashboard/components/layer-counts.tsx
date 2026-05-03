import type { Layer, RowCounts } from "@/lib/data";

const LAYER_DESCRIPTIONS: Record<Layer, string> = {
  bronze: "Raw CSV ingest as STRING + provenance metadata. Append-only.",
  silver: "Typed casts + dedup keep-latest by silver_loaded_at.",
  gold: "RWA aggregation + 4-dimension DQ scorecard mart.",
};

type LayerCountsProps = {
  rowCounts: RowCounts;
};

export function LayerCounts({ rowCounts }: LayerCountsProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {(Object.keys(rowCounts) as Layer[]).map((layer) => {
        const tables = rowCounts[layer];
        const total = Object.values(tables).reduce((acc, n) => acc + n, 0);
        return (
          <div
            key={layer}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] p-4"
          >
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide">
                {layer}
              </h3>
              <span className="text-xs text-[var(--color-muted-foreground)] tabular-nums">
                {total.toLocaleString()} rows
              </span>
            </div>
            <p className="mt-1 text-xs text-[var(--color-muted-foreground)]">
              {LAYER_DESCRIPTIONS[layer]}
            </p>
            <ul className="mt-3 space-y-1 text-xs font-mono">
              {Object.entries(tables).map(([table, count]) => (
                <li key={table} className="flex justify-between">
                  <span className="text-[var(--color-muted-foreground)]">
                    {table}
                  </span>
                  <span className="tabular-nums">{count.toLocaleString()}</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
