import { TriangleAlert } from "lucide-react";

export function SyntheticDisclaimer() {
  return (
    <div
      role="note"
      className="rounded-md border border-[var(--color-border)] bg-[var(--color-muted)] px-4 py-3 text-sm text-[var(--color-muted-foreground)] flex items-start gap-2"
    >
      <TriangleAlert
        size={16}
        aria-hidden="true"
        className="mt-0.5 shrink-0 text-[var(--color-warning)]"
      />
      <p>
        <span className="font-medium text-[var(--color-foreground)]">
          Synthetic data only.
        </span>{" "}
        Every counterparty here is a deterministic fake — LEIs all begin{" "}
        <code>9999</code>, names like <code>AcmeBank S.A.</code>, generated from{" "}
        <code>seed=42</code>. No real G-SIB data, no production claims.
      </p>
    </div>
  );
}
