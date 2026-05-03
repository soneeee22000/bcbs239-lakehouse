import { cn } from "@/lib/utils";
import { formatPct, severityFor, type ScoreSeverity } from "@/lib/data";

const SEVERITY_RING: Record<ScoreSeverity, string> = {
  good: "ring-[var(--color-success)]/30",
  warn: "ring-[var(--color-warning)]/40",
  bad: "ring-[var(--color-danger)]/50",
};

const SEVERITY_TEXT: Record<ScoreSeverity, string> = {
  good: "text-[var(--color-success)]",
  warn: "text-[var(--color-warning)]",
  bad: "text-[var(--color-danger)]",
};

type ScoreTileProps = {
  label: string;
  score: number;
  detail?: string;
};

export function ScoreTile({ label, score, detail }: ScoreTileProps) {
  const severity = severityFor(score);
  return (
    <div
      className={cn(
        "rounded-lg border bg-[var(--color-background)] px-4 py-4 ring-1",
        SEVERITY_RING[severity],
      )}
    >
      <p className="text-xs uppercase tracking-wide text-[var(--color-muted-foreground)]">
        {label}
      </p>
      <p
        className={cn(
          "mt-1 text-3xl font-semibold tabular-nums",
          SEVERITY_TEXT[severity],
        )}
      >
        {formatPct(score)}
      </p>
      {detail ? (
        <p className="mt-1 text-xs text-[var(--color-muted-foreground)]">
          {detail}
        </p>
      ) : null}
    </div>
  );
}
