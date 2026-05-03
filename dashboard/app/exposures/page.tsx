import type { Metadata } from "next";
import { RwaTable } from "@/components/rwa-table";
import { SyntheticDisclaimer } from "@/components/synthetic-disclaimer";
import { RWA_TOP, formatEur } from "@/lib/data";

export const metadata: Metadata = {
  title: "Exposures · bcbs239-lakehouse",
  description:
    "Top RWA aggregations from the bcbs239-lakehouse Gold mart. Synthetic counterparties only — LEI prefix 9999.",
};

export default function ExposuresPage() {
  const totalRwa = RWA_TOP.reduce((acc, r) => acc + r.total_rwa_eur, 0);
  const totalExposures = RWA_TOP.reduce((acc, r) => acc + r.exposure_count, 0);
  const totalAmount = RWA_TOP.reduce((acc, r) => acc + r.total_amount_eur, 0);

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-8 sm:py-12 space-y-10">
      <header className="space-y-2">
        <p className="text-xs uppercase tracking-wide text-[var(--color-muted-foreground)]">
          Gold mart · fact_rwa_aggregation
        </p>
        <h1 className="text-3xl font-bold tracking-tight">Exposures</h1>
        <p className="text-base text-[var(--color-muted-foreground)] max-w-3xl">
          Top {RWA_TOP.length} risk-weighted-asset rollups by total RWA EUR,
          grouped by counterparty (LEI) × exposure type × as-of date. Computed
          from <code>silver.exposure</code> as{" "}
          <code>sum(amount_eur × risk_weight)</code>.
        </p>
      </header>

      <SyntheticDisclaimer />

      <section className="grid grid-cols-3 gap-3">
        <Stat label="Top-N rows" value={RWA_TOP.length.toLocaleString()} />
        <Stat label="Total RWA" value={formatEur(totalRwa)} />
        <Stat label="Exposures" value={totalExposures.toLocaleString()} />
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Top {RWA_TOP.length} by RWA</h2>
        <RwaTable rows={RWA_TOP} limit={RWA_TOP.length} />
        <p className="text-xs text-[var(--color-muted-foreground)]">
          Total notional in this top-N: {formatEur(totalAmount)}. Numbers
          reflect a single re-run of the synthetic generator with seed=42; in a
          real G-SIB engagement, this mart would join out to the counterparty
          master and segment by IFRS 9 stage / regulatory treatment.
        </p>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] p-4">
      <p className="text-xs uppercase tracking-wide text-[var(--color-muted-foreground)]">
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}
