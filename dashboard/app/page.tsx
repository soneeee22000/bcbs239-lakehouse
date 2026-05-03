import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { ArchitectureFlow } from "@/components/architecture-flow";
import { DriftTable } from "@/components/drift-table";
import { LayerCounts } from "@/components/layer-counts";
import { ScoreTile } from "@/components/score-tile";
import { SyntheticDisclaimer } from "@/components/synthetic-disclaimer";
import {
  EXTRACTED_AT,
  ROW_COUNTS,
  averageScoreByDimension,
  getDriftPair,
  getLatestSnapshot,
} from "@/lib/data";

export default function HomePage() {
  const latest = getLatestSnapshot();
  const drift = getDriftPair();

  const formattedExtractedAt = new Date(EXTRACTED_AT).toLocaleString("en-GB", {
    timeZone: "UTC",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-8 sm:py-12 space-y-12">
      <Hero />

      <SyntheticDisclaimer />

      {latest ? (
        <section aria-labelledby="scores-heading" className="space-y-3">
          <header className="flex items-baseline justify-between gap-2 flex-wrap">
            <h2 id="scores-heading" className="text-xl font-semibold">
              DQ scorecard — latest snapshot
            </h2>
            <p className="text-xs text-[var(--color-muted-foreground)]">
              snapshot {latest.label} · extracted {formattedExtractedAt}
            </p>
          </header>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <ScoreTile
              label="Completeness"
              score={averageScoreByDimension(latest, "completeness")}
              detail="required fields non-null"
            />
            <ScoreTile
              label="Integrity"
              score={averageScoreByDimension(latest, "integrity")}
              detail="natural-key uniqueness"
            />
            <ScoreTile
              label="Accuracy"
              score={averageScoreByDimension(latest, "accuracy")}
              detail="value-range checks"
            />
            <ScoreTile
              label="Timeliness"
              score={averageScoreByDimension(latest, "timeliness")}
              detail="snapshot freshness"
            />
          </div>
          <p className="text-xs text-[var(--color-muted-foreground)]">
            Tile averages each dimension across all 3 sources (counterparty,
            exposure, collateral). Per-row breakdown in the{" "}
            <Link className="inline-link underline" href="/scorecard">
              scorecard
            </Link>{" "}
            page.
          </p>
        </section>
      ) : null}

      {drift ? (
        <section aria-labelledby="drift-heading" className="space-y-3">
          <header className="flex items-baseline justify-between gap-2 flex-wrap">
            <h2 id="drift-heading" className="text-xl font-semibold">
              Defect injection — scorecard reacts
            </h2>
            <p className="text-xs text-[var(--color-muted-foreground)]">
              T1 = clean synthetic data · T2 = same generator with
              cleanliness=0.7
            </p>
          </header>
          <DriftTable t1={drift.t1} t2={drift.t2} />
          <p className="text-xs text-[var(--color-muted-foreground)]">
            The defect-injection rules in <code>synthetic.py</code> only break
            two scorers — out-of-range risk weights surface in{" "}
            <code>exposure.accuracy</code>, stale valuations surface in{" "}
            <code>collateral.timeliness</code>. The other 8 dimensions hold at
            100% because the rules don&apos;t produce nulls or duplicate natural
            keys.
          </p>
        </section>
      ) : null}

      <section aria-labelledby="layers-heading" className="space-y-3">
        <h2 id="layers-heading" className="text-xl font-semibold">
          Medallion layers — Bronze → Silver → Gold
        </h2>
        <p className="text-sm text-[var(--color-muted-foreground)]">
          Live row counts from the <code>bcbs239_lakehouse</code> Unity Catalog
          on Databricks Free Edition. Bronze is append-only (so re-runs grow
          it); Silver dedupes by natural key keeping the latest{" "}
          <code>silver_loaded_at</code>.
        </p>
        <LayerCounts rowCounts={ROW_COUNTS} />
      </section>

      <ArchitectureSection />

      <ScopeSection />
    </div>
  );
}

function Hero() {
  return (
    <section className="space-y-4">
      <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">
        bcbs239-lakehouse
      </h1>
      <p className="text-lg text-[var(--color-muted-foreground)] max-w-3xl">
        Reference implementation of the BCBS 239 risk-data-aggregation lakehouse
        pattern Capgemini Risk Data Insights and Big-4 BCBS 239 advisory
        practices recommend G-SIBs build atop Databricks Unity Catalog.
        Portfolio piece — synthetic data only, MIT.
      </p>
      <div className="flex flex-wrap gap-2">
        <Link
          href="/scorecard"
          className="inline-flex items-center gap-1 rounded-md bg-[var(--color-primary)] text-[var(--color-primary-foreground)] px-4 py-2 text-sm font-medium"
        >
          DQ scorecard
          <ArrowRight size={14} aria-hidden="true" />
        </Link>
        <Link
          href="/pipeline"
          className="inline-flex items-center gap-1 rounded-md border border-[var(--color-border)] px-4 py-2 text-sm font-medium hover:bg-[var(--color-muted)]"
        >
          Pipeline
          <ArrowRight size={14} aria-hidden="true" />
        </Link>
        <a
          href="https://github.com/soneeee22000/bcbs239-lakehouse"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-md border border-[var(--color-border)] px-4 py-2 text-sm font-medium hover:bg-[var(--color-muted)]"
        >
          GitHub
          <ArrowRight size={14} aria-hidden="true" />
        </a>
      </div>
    </section>
  );
}

function ArchitectureSection() {
  return (
    <section aria-labelledby="architecture-heading" className="space-y-3">
      <h2 id="architecture-heading" className="text-xl font-semibold">
        Architecture
      </h2>
      <ArchitectureFlow />
      <p className="text-xs text-[var(--color-muted-foreground)]">
        Two execution paths share one storage format (Delta Lake). The library
        path runs locally on Polars + delta-rs (no JVM, full CI coverage). The
        Databricks runtime path runs on PySpark + delta-spark inside Free
        Edition serverless notebooks. See{" "}
        <a
          className="inline-link underline"
          href="https://github.com/soneeee22000/bcbs239-lakehouse/blob/main/docs/PORTABILITY.md"
          target="_blank"
          rel="noopener noreferrer"
        >
          PORTABILITY.md
        </a>{" "}
        for the Snowflake-stack equivalence matrix.
      </p>
    </section>
  );
}

function ScopeSection() {
  return (
    <section aria-labelledby="scope-heading" className="space-y-3">
      <h2 id="scope-heading" className="text-xl font-semibold">
        What&apos;s covered, what isn&apos;t
      </h2>
      <p className="text-sm text-[var(--color-muted-foreground)]">
        BCBS 239 has 14 principles. This project implements the 4 that have a
        defensible software-engineerable surface — the rest are governance,
        organisation, and supervisory concerns that no software ships.
      </p>
      <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
        <table className="w-full text-sm">
          <thead className="bg-[var(--color-muted)] text-left">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">
                Principle
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Status
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Implementation
              </th>
            </tr>
          </thead>
          <tbody>
            {[
              {
                p: "#3 Accuracy & integrity",
                s: "in",
                impl: "score_accuracy_value_in_range scorer",
              },
              {
                p: "#5 Completeness",
                s: "in",
                impl: "score_completeness (required-field non-null)",
              },
              {
                p: "#6 Timeliness",
                s: "in",
                impl: "score_timeliness (snapshot freshness)",
              },
              {
                p: "#4 Integrity (deduplication)",
                s: "in",
                impl: "score_integrity_dedup (natural-key uniqueness)",
              },
              {
                p: "#1 Governance, #2 Data architecture & IT",
                s: "out",
                impl: "Organisational; out of scope for any software",
              },
              {
                p: "#7-11 Risk reporting practices",
                s: "out",
                impl: "Reporting-side; project #3 territory",
              },
              {
                p: "#12-14 Supervisory review",
                s: "out",
                impl: "Regulator-side, not buildable",
              },
            ].map((row) => (
              <tr key={row.p} className="border-t border-[var(--color-border)]">
                <td className="px-3 py-2">{row.p}</td>
                <td className="px-3 py-2">
                  <span
                    className={
                      row.s === "in"
                        ? "text-[var(--color-success)] font-medium"
                        : "text-[var(--color-muted-foreground)]"
                    }
                  >
                    {row.s === "in" ? "In scope" : "Out of scope"}
                  </span>
                </td>
                <td className="px-3 py-2 text-xs text-[var(--color-muted-foreground)]">
                  {row.impl}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
