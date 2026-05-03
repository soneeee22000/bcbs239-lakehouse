import type { Metadata } from "next";
import { ArchitectureFlow } from "@/components/architecture-flow";
import { LayerCounts } from "@/components/layer-counts";
import { SyntheticDisclaimer } from "@/components/synthetic-disclaimer";
import { CATALOG, ROW_COUNTS } from "@/lib/data";

export const metadata: Metadata = {
  title: "Pipeline · bcbs239-lakehouse",
  description:
    "Bronze → Silver → Gold medallion pipeline for the bcbs239-lakehouse reference. Live row counts from the Databricks Free Edition workspace.",
};

export default function PipelinePage() {
  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-8 sm:py-12 space-y-10">
      <header className="space-y-2">
        <p className="text-xs uppercase tracking-wide text-[var(--color-muted-foreground)]">
          Medallion architecture
        </p>
        <h1 className="text-3xl font-bold tracking-tight">Pipeline</h1>
        <p className="text-base text-[var(--color-muted-foreground)] max-w-3xl">
          Bronze → Silver → Gold over Delta Lake on Databricks Free Edition. The
          same logic runs locally on Polars + delta-rs for CI; the notebooks
          path runs PySpark on Free Edition serverless. Both write
          byte-compatible Delta tables.
        </p>
      </header>

      <SyntheticDisclaimer />

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Live row counts</h2>
        <p className="text-sm text-[var(--color-muted-foreground)]">
          From the <code>{CATALOG}</code> Unity Catalog. After{" "}
          <code>make refresh</code> on dirty CSVs, Bronze grows to ~2× its clean
          size (append-only); Silver and Gold replace contents (overwrite) so
          they reflect the latest dedup&apos;d state.
        </p>
        <LayerCounts rowCounts={ROW_COUNTS} />
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Stage flow</h2>
        <ArchitectureFlow />
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Stage details</h2>
        <StageDetail
          stage="Bronze"
          contract="Preserve raw bytes — every CSV column read as STRING. Append-only Delta. Adds _source_file + _ingest_ts metadata."
          notebookFile="notebooks/01_bronze.py"
          libraryFile="src/bcbs239_lakehouse/pipeline/bronze.py"
          why="Defers all type coercion to Silver. Out-of-range values, malformed dates, future maturities all flow through unchanged so the DQ scorecard can see them."
        />
        <StageDetail
          stage="Silver"
          contract="Typed casts (DOUBLE, DATE, INT). Strip _source_file, rename _ingest_ts → silver_loaded_at. Window-function dedup keeps the latest row per natural key."
          notebookFile="notebooks/02_silver.py"
          libraryFile="src/bcbs239_lakehouse/pipeline/silver.py"
          why="Business-rule violations are PRESERVED. Negative amounts, future maturities, broken FKs survive into Silver — Gold's DQ scorecard surfaces them as score drops."
        />
        <StageDetail
          stage="Gold"
          contract="fact_rwa_aggregation: GROUP BY lei × exposure_type × as_of_date with sum(amount × risk_weight). fact_dq_scorecard: 4 dimensions × 3 sources, append-snapshot per refresh."
          notebookFile="notebooks/03_gold.py"
          libraryFile="src/bcbs239_lakehouse/pipeline/gold.py"
          why="Append-snapshot pattern means each refresh adds a row per (source, dimension). Two snapshots = clean-vs-dirty drift demo."
        />
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Reproduce locally</h2>
        <pre className="rounded-lg border border-[var(--color-border)] bg-[var(--color-muted)] p-4 text-xs font-mono overflow-x-auto">
          {`# Local — no Databricks needed
make setup
make demo                  # synthetic -> bronze -> silver -> gold (Polars + delta-rs)

# Live Databricks Free Edition
cp .env.example .env       # fill in DATABRICKS_HOST + DATABRICKS_TOKEN
make uc-provision          # catalog + bronze/silver/gold/raw schemas + raw.synthetic volume
make synthetic
make uc-data-upload        # push clean CSVs to /Volumes/{catalog}/raw/synthetic/
# (Workspace UI: import notebooks/01_bronze.py / 02_silver.py / 03_gold.py and Run all)
make lakeview-provision    # publish the BCBS 239 DQ Scorecard dashboard

# Defect-injection demo loop
make inject-defects && make uc-data-upload && make refresh`}
        </pre>
      </section>
    </div>
  );
}

type StageDetailProps = {
  stage: string;
  contract: string;
  notebookFile: string;
  libraryFile: string;
  why: string;
};

function StageDetail({
  stage,
  contract,
  notebookFile,
  libraryFile,
  why,
}: StageDetailProps) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] p-4 space-y-2">
      <h3 className="text-base font-semibold">{stage}</h3>
      <p className="text-sm">{contract}</p>
      <dl className="text-xs grid sm:grid-cols-2 gap-x-4 gap-y-1 font-mono">
        <div>
          <dt className="inline text-[var(--color-muted-foreground)]">
            notebook ·{" "}
          </dt>
          <dd className="inline">{notebookFile}</dd>
        </div>
        <div>
          <dt className="inline text-[var(--color-muted-foreground)]">
            library ·{" "}
          </dt>
          <dd className="inline">{libraryFile}</dd>
        </div>
      </dl>
      <p className="text-xs text-[var(--color-muted-foreground)]">{why}</p>
    </div>
  );
}
