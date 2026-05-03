import {
  formatPct,
  indexBySourceDimension,
  severityFor,
  type DqDimension,
  type DqSource,
  type ScorecardSnapshot,
} from "@/lib/data";
import { cn } from "@/lib/utils";

const SOURCES: DqSource[] = ["counterparty", "exposure", "collateral"];
const DIMENSIONS: DqDimension[] = [
  "completeness",
  "integrity",
  "accuracy",
  "timeliness",
];

const CELL_TINT = {
  good: "",
  warn: "text-[var(--color-warning)] font-medium",
  bad: "text-[var(--color-danger)] font-semibold",
};

type DriftTableProps = {
  t1: ScorecardSnapshot;
  t2: ScorecardSnapshot;
};

export function DriftTable({ t1, t2 }: DriftTableProps) {
  const t1Map = indexBySourceDimension(t1);
  const t2Map = indexBySourceDimension(t2);
  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
      <table className="w-full text-sm">
        <caption className="sr-only">
          DQ scorecard drift from snapshot T1 (clean) to T2 (defect-injected).
        </caption>
        <thead className="bg-[var(--color-muted)] text-left">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              Source
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Dimension
            </th>
            <th scope="col" className="px-3 py-2 font-medium text-right">
              T1 clean
            </th>
            <th scope="col" className="px-3 py-2 font-medium text-right">
              T2 dirty
            </th>
            <th scope="col" className="px-3 py-2 font-medium text-right">
              Δ
            </th>
            <th scope="col" className="px-3 py-2 font-medium text-right">
              Failed (T2)
            </th>
          </tr>
        </thead>
        <tbody>
          {SOURCES.flatMap((source) =>
            DIMENSIONS.map((dim) => {
              const key = `${source}.${dim}`;
              const t1Score = t1Map.get(key);
              const t2Score = t2Map.get(key);
              if (!t1Score && !t2Score) return null;
              const t1V = t1Score?.score ?? null;
              const t2V = t2Score?.score ?? null;
              const delta = t1V !== null && t2V !== null ? t2V - t1V : null;
              const sev = t2V !== null ? severityFor(t2V) : "good";
              return (
                <tr
                  key={key}
                  className="border-t border-[var(--color-border)] hover:bg-[var(--color-muted)]/40"
                >
                  <td className="px-3 py-2 font-mono text-xs">{source}</td>
                  <td className="px-3 py-2">{dim}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {t1V === null ? "—" : formatPct(t1V)}
                  </td>
                  <td
                    className={cn(
                      "px-3 py-2 text-right tabular-nums",
                      CELL_TINT[sev],
                    )}
                  >
                    {t2V === null ? "—" : formatPct(t2V)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-xs">
                    {delta === null
                      ? "—"
                      : delta === 0
                        ? "—"
                        : `${delta > 0 ? "+" : ""}${(delta * 100).toFixed(1)} pp`}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-xs text-[var(--color-muted-foreground)]">
                    {t2Score?.failed_count ?? 0} / {t2Score?.sample_size ?? 0}
                  </td>
                </tr>
              );
            }),
          )}
        </tbody>
      </table>
    </div>
  );
}
