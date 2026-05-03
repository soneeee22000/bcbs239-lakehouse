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

      <WhyBcbs239Section />

      <RwaPrimerSection />

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

      <TwoMartPatternSection />

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

function WhyBcbs239Section() {
  return (
    <section aria-labelledby="why-heading" className="space-y-3">
      <h2 id="why-heading" className="text-xl font-semibold">
        What is BCBS 239?
      </h2>
      <div className="space-y-3 text-sm sm:text-base text-[var(--color-foreground)] max-w-3xl">
        <p>
          BCBS 239 is a 14-principle Basel Committee regulation from 2013 that
          requires the world&apos;s 30 largest banks (G-SIBs) to demonstrate to
          regulators that they aggregate risk data{" "}
          <strong>accurately, completely, and on time</strong> across legal
          entities, risk types, and reporting periods.
        </p>
        <p>
          Of the 14 principles, only{" "}
          <strong>4 have a defensible software surface</strong> — completeness,
          accuracy, timeliness, and integrity. The other 10 are governance,
          organisational, and supervisory concerns that no software ships. This
          project implements the 4 a data engineer can actually build.
        </p>
        <p className="text-[var(--color-muted-foreground)]">
          Every G-SIB runs a multi-year BCBS 239 maturity programme. French
          banks (BNP Paribas, Société Générale, BPCE, Crédit Agricole) build
          internal evidence layers; advisory practices sell implementation
          engagements around them. This repo is a public reference
          implementation of that pattern on Databricks Free Edition.
        </p>
      </div>
    </section>
  );
}

function RwaPrimerSection() {
  return (
    <section aria-labelledby="rwa-heading" className="space-y-3">
      <h2 id="rwa-heading" className="text-xl font-semibold">
        Risk-weighted assets, in 60 seconds
      </h2>
      <div className="space-y-3 text-sm sm:text-base text-[var(--color-foreground)] max-w-3xl">
        <p>
          A bank can&apos;t say &quot;we have €1bn in loans&quot; — a €1bn loan
          to the German government is far less risky than a €1bn unsecured SME
          loan. So Basel says: multiply each exposure by a risk weight
          reflecting how dangerous it is, then sum.
        </p>
        <pre className="overflow-x-auto rounded-md border border-[var(--color-border)] bg-[var(--color-muted)] px-4 py-3 text-sm">
          <code>RWA = Σ (exposure_amount × risk_weight)</code>
        </pre>
        <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
          <table className="w-full text-sm">
            <thead className="bg-[var(--color-muted)] text-left">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  Asset class
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Typical risk weight
                </th>
              </tr>
            </thead>
            <tbody>
              {[
                { c: "Cash, AAA government debt", w: "0%" },
                { c: "Residential mortgages", w: "~35%" },
                { c: "Investment-grade corporate loans", w: "100%" },
                { c: "Speculative-grade / distressed", w: "150%" },
              ].map((row) => (
                <tr
                  key={row.c}
                  className="border-t border-[var(--color-border)]"
                >
                  <td className="px-3 py-2">{row.c}</td>
                  <td className="px-3 py-2 font-mono text-xs">{row.w}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          Banks must hold regulatory capital ≥ a fixed percentage of their RWA
          (8% under Basel III, plus buffers ≈ 10.5–13%). RWA is the{" "}
          <strong>denominator of every capital-adequacy ratio</strong> banks
          publish.
        </p>
        <p className="text-[var(--color-muted-foreground)]">
          The arithmetic is trivial. The BCBS 239 problem is the data plumbing:
          can a G-SIB pull every exposure across every legal entity, every desk,
          every system, and roll it up correctly with auditable lineage when the
          regulator asks? That&apos;s what this lakehouse pattern is for.
        </p>
      </div>
    </section>
  );
}

function TwoMartPatternSection() {
  return (
    <section aria-labelledby="two-mart-heading" className="space-y-3">
      <h2 id="two-mart-heading" className="text-xl font-semibold">
        Two-mart pattern: business answer + trust signal
      </h2>
      <div className="space-y-3 text-sm sm:text-base text-[var(--color-foreground)] max-w-3xl">
        <p>
          The Gold layer produces two parallel marts. That separation is the
          BCBS 239 thesis in one design choice:
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] p-4 space-y-2">
            <p className="text-xs uppercase tracking-wide text-[var(--color-muted-foreground)]">
              The business answer
            </p>
            <p className="font-mono text-sm">fact_rwa_aggregation</p>
            <p className="text-sm">
              For each (legal entity, exposure type, reporting date), aggregate{" "}
              <code>amount_eur × risk_weight</code>. 222 rows on the synthetic
              data —{" "}
              <Link className="inline-link underline" href="/exposures">
                browse the top entries
              </Link>
              .
            </p>
          </div>
          <div className="rounded-lg border border-[var(--color-border)] p-4 space-y-2">
            <p className="text-xs uppercase tracking-wide text-[var(--color-muted-foreground)]">
              The trust signal
            </p>
            <p className="font-mono text-sm">fact_dq_scorecard</p>
            <p className="text-sm">
              For the same snapshot, score completeness, accuracy, timeliness,
              integrity. 10 rows per pipeline run — the tiles{" "}
              <span aria-hidden="true">↑</span> read this mart.
            </p>
          </div>
        </div>
        <p>
          Bad rows (negative amounts, out-of-range risk weights) are{" "}
          <em>still aggregated</em> into the business mart — the resulting
          figures are wrong on dirty data, which is precisely the point: the
          scorecard quantifies the wrongness independently. A regulator looking
          at an RWA number wants to see, side by side, how trustworthy the
          inputs were. That is the BCBS 239 evidence layer.
        </p>
      </div>
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
