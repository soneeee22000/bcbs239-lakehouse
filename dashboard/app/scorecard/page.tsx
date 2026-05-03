import type { Metadata } from "next";
import Link from "next/link";
import { DriftTable } from "@/components/drift-table";
import { ScoreTile } from "@/components/score-tile";
import { SyntheticDisclaimer } from "@/components/synthetic-disclaimer";
import {
  averageScoreByDimension,
  formatPct,
  getDriftPair,
  getLatestSnapshot,
  type DqDimension,
} from "@/lib/data";

export const metadata: Metadata = {
  title: "DQ scorecard · bcbs239-lakehouse",
  description:
    "BCBS 239 DQ scorecard for the bcbs239-lakehouse reference. Latest snapshot per (source, dimension), with clean-vs-dirty drift comparison.",
};

const SCORER_DESCRIPTIONS: Record<DqDimension, string> = {
  completeness:
    "Required fields non-null. Per source: counterparty needs lei, legal_name, country_iso2, sector; exposure needs exposure_id, lei, amount_eur, risk_weight, as_of_date; collateral needs collateral_id, exposure_id, value_eur, valuation_date.",
  integrity:
    "Natural-key uniqueness — count(*) = count(distinct natural_key). Caught by Silver dedup but scored on Silver to surface upstream merge bugs.",
  accuracy:
    "Value-range checks. Exposure: risk_weight ∈ [0, 1.5]. Collateral: haircut_pct ∈ [0, 1]. The defect-injection generator deliberately breaks both ranges in 30% of rows.",
  timeliness:
    "Freshness against the latest snapshot. Exposure: every as_of_date matches max(as_of_date). Collateral: valuation_date within 180 days of max(valuation_date). The defect-injection generator backdates valuations beyond the window.",
};

export default function ScorecardPage() {
  const latest = getLatestSnapshot();
  const drift = getDriftPair();

  if (!latest) {
    return (
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-12">
        <p>
          No scorecard snapshots yet. Run{" "}
          <code>
            make refresh && python dashboard/scripts/export_dashboard_data.py
          </code>
          .
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-8 sm:py-12 space-y-10">
      <header className="space-y-2">
        <p className="text-xs uppercase tracking-wide text-[var(--color-muted-foreground)]">
          BCBS 239 data quality
        </p>
        <h1 className="text-3xl font-bold tracking-tight">DQ scorecard</h1>
        <p className="text-base text-[var(--color-muted-foreground)] max-w-3xl">
          Four BCBS 239 data-engineerable principles scored against the Silver
          layer of the bcbs239_lakehouse Unity Catalog. Each row pairs a source
          (counterparty / exposure / collateral) with a dimension. Synthetic
          data only.
        </p>
      </header>

      <SyntheticDisclaimer />

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Latest snapshot averages</h2>
        <p className="text-xs text-[var(--color-muted-foreground)]">
          Snapshot {latest.label} ·{" "}
          <code>{new Date(latest.snapshot_ts).toISOString()}</code>
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {(
            ["completeness", "integrity", "accuracy", "timeliness"] as const
          ).map((dim) => (
            <ScoreTile
              key={dim}
              label={dim}
              score={averageScoreByDimension(latest, dim)}
              detail={`avg over 3 sources`}
            />
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">
          Per (source, dimension) — latest
        </h2>
        <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
          <table className="w-full text-sm">
            <caption className="sr-only">
              Latest DQ scorecard snapshot, one row per (source, dimension).
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
                  Score
                </th>
                <th scope="col" className="px-3 py-2 font-medium text-right">
                  Sample
                </th>
                <th scope="col" className="px-3 py-2 font-medium text-right">
                  Failed
                </th>
              </tr>
            </thead>
            <tbody>
              {latest.dimensions.map((row) => (
                <tr
                  key={`${row.source}.${row.dimension}`}
                  className="border-t border-[var(--color-border)]"
                >
                  <td className="px-3 py-2 font-mono text-xs">{row.source}</td>
                  <td className="px-3 py-2">{row.dimension}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-medium">
                    {formatPct(row.score)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-xs text-[var(--color-muted-foreground)]">
                    {row.sample_size}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-xs text-[var(--color-muted-foreground)]">
                    {row.failed_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {drift ? (
        <section className="space-y-3">
          <h2 className="text-xl font-semibold">Clean vs dirty drift</h2>
          <p className="text-sm text-[var(--color-muted-foreground)]">
            Same query, two snapshots — <code>{drift.t1.label}</code> ran on the
            deterministic clean generator (cleanliness=1.0);{" "}
            <code>{drift.t2.label}</code> ran on the same generator with
            cleanliness=0.7 (PRD Story 3 defect injection).
          </p>
          <DriftTable t1={drift.t1} t2={drift.t2} />
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Scorer definitions</h2>
        <dl className="space-y-3">
          {(
            ["completeness", "integrity", "accuracy", "timeliness"] as const
          ).map((dim) => (
            <div
              key={dim}
              className="rounded-lg border border-[var(--color-border)] p-4"
            >
              <dt className="font-semibold capitalize">{dim}</dt>
              <dd className="mt-1 text-sm text-[var(--color-muted-foreground)]">
                {SCORER_DESCRIPTIONS[dim]}
              </dd>
            </div>
          ))}
        </dl>
        <p className="text-xs text-[var(--color-muted-foreground)]">
          Source:{" "}
          <Link
            className="inline-link underline"
            href="https://github.com/soneeee22000/bcbs239-lakehouse/blob/main/src/bcbs239_lakehouse/quality/dimensions.py"
          >
            src/bcbs239_lakehouse/quality/dimensions.py
          </Link>
          . The PySpark mirror in <code>notebooks/03_gold.py</code> reproduces
          the same logic for the Databricks-runtime path.
        </p>
      </section>
    </div>
  );
}
