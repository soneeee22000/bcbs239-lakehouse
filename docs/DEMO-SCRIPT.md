# Demo script — bcbs239-lakehouse on Databricks

What to capture, in what order, with what caption — for the recruiter pitch
or Loom walkthrough. Targets a 60-90 second narrative arc:

> "Real BCBS 239 risk-data-aggregation pattern, running on a real Databricks
> Free Edition workspace with Unity Catalog and Delta Lake. Watch the DQ
> scorecard react to upstream data drift on synthetic counterparty + exposure
>
> - collateral data."

All numbers below come from the live workspace at
`https://dbc-8e08270c-6eda.cloud.databricks.com/explore/data/bcbs239_lakehouse`.
Synthetic data only — every claim is on synthetic data.

---

## Capture order

The narrative goes: **architecture → ingestion → quality drift → reaction**.

### 1. Catalog tree (still — 1 screenshot)

**URL:** `https://dbc-8e08270c-6eda.cloud.databricks.com/explore/data/bcbs239_lakehouse`

**What to show:** Catalog Explorer, left tree expanded to:

```
bcbs239_lakehouse
├── bronze (3 tables)
├── silver (3 tables)
├── gold (2 tables)
└── raw (volume: synthetic with 3 .csv files)
```

**Caption:** _"Unity Catalog medallion layout — synthetic risk data lands in
`raw.synthetic` (volume), flows through `bronze`, `silver`, `gold` schemas.
Schemas + volume are provisioned by `make uc-provision` (one Python module,
idempotent SDK calls)."_

### 2. Bronze table preview (still — 1 screenshot)

**URL:** `https://dbc-8e08270c-6eda.cloud.databricks.com/explore/data/bcbs239_lakehouse/bronze/exposure`

**What to show:** Catalog Explorer → bronze.exposure → **Sample Data** tab.
Columns visible should include: `exposure_id`, `lei`, `exposure_type`,
`amount_eur` (string), `risk_weight` (string), and the metadata cols
`_source_file = "exposure.csv"`, `_ingest_ts = <timestamp>`.

**Caption:** _"Bronze contract — every CSV column preserved as STRING with
`_source_file` and `_ingest_ts` provenance metadata. Append-only Delta. No
typed casts at this layer; raw bytes only."_

### 3. Silver typed schema (still — 1 screenshot)

**URL:** `https://dbc-8e08270c-6eda.cloud.databricks.com/explore/data/bcbs239_lakehouse/silver/exposure`

**What to show:** Same table, **Schema** tab. Columns now have proper types:
`amount_eur DOUBLE`, `risk_weight DOUBLE`, `as_of_date DATE`,
`maturity_date DATE`, `internal_rating INT`, `silver_loaded_at TIMESTAMP`.

**Caption:** _"Silver layer applies typed casts and dedups on the natural key
keeping the latest `silver_loaded_at` row. Business-rule violations (negative
amounts, future maturities, out-of-range risk weights) are intentionally
preserved — Gold's DQ scorecard surfaces them."_

### 4. Gold DQ scorecard — drift (still — 1 screenshot, the money shot)

**URL:** SQL Editor (`https://dbc-8e08270c-6eda.cloud.databricks.com/sql/editor`)

**Query:**

```sql
WITH snaps AS (
  SELECT DISTINCT snapshot_ts FROM bcbs239_lakehouse.gold.fact_dq_scorecard
),
labeled AS (
  SELECT s.snapshot_ts,
         CASE WHEN s.snapshot_ts = (SELECT min(snapshot_ts) FROM snaps)
              THEN 'T1_clean' ELSE 'T2_dirty' END AS label,
         f.source, f.dimension, f.score, f.failed_count
  FROM snaps s
  JOIN bcbs239_lakehouse.gold.fact_dq_scorecard f USING (snapshot_ts)
)
SELECT source, dimension,
       MAX(CASE WHEN label = 'T1_clean' THEN ROUND(score, 4) END) AS T1_clean,
       MAX(CASE WHEN label = 'T2_dirty' THEN ROUND(score, 4) END) AS T2_dirty,
       MAX(CASE WHEN label = 'T1_clean' THEN failed_count END) AS T1_fails,
       MAX(CASE WHEN label = 'T2_dirty' THEN failed_count END) AS T2_fails
FROM labeled
GROUP BY source, dimension
ORDER BY source, dimension;
```

**What to show:** the result grid with the two visibly dropped scores
highlighted:

| source     | dimension      | T1_clean | T2_dirty | T1_fails | T2_fails |
| ---------- | -------------- | -------- | -------- | -------- | -------- |
| collateral | timeliness     | **1.00** | **0.11** | 0        | **356**  |
| exposure   | accuracy       | **1.00** | **0.91** | 0        | **28**   |
| (others)   | (8 dimensions) | 1.00     | 1.00     | 0        | 0        |

**Caption:** _"Same Gold mart, two snapshots, same query. After
`make inject-defects` regenerates synthetic CSVs with `cleanliness=0.7` and
the pipeline re-runs, `collateral.timeliness` drops from 100% to 11% (356 of
400 rows beyond the 180-day valuation window) and `exposure.accuracy` drops
from 100% to 91% (28 risk weights outside [0, 1.5]). Other dimensions stay
clean — the defect-injection rules only break the two scorers above."_

### 5. (Optional, ~30s GIF) terminal-driven defect loop

**Tool:** ScreenToGif / asciinema / built-in OS recorder.

**Steps to record:**

```bash
# 1. (already shown clean state in screenshot 4)
make inject-defects        # regenerates dirty synthetic CSVs locally
make uc-data-upload        # pushes to /Volumes/.../raw/synthetic/
make refresh               # runs Bronze→Silver→Gold + appends new scorecard snapshot
```

Then cut to the SQL Editor, hit **Run**, the dropped scores appear.

**Caption:** _"3 commands, ~15 seconds end-to-end on Free Edition serverless.
The full Bronze→Silver→Gold refresh is `scripts/refresh_pipeline.py` —
~150 lines of Spark SQL via the Statement Execution API, equivalent to
`notebooks/{01_bronze, 02_silver, 03_gold}.py` but terminal-driven for the
demo loop."_

---

## What NOT to show

- The Catalog Explorer "samples.bakehouse" Delta share (irrelevant, distracts)
- The serverless-spin-up Waiting state (boring)
- The `_rescued_data` column from `read_files()` (implementation detail)
- The 0-byte initial commit of `docs/DEPLOY.md` (embarrassing — was fixed in
  commit `08c6cba`)
- Any framing that overstates scope: this is **a reference implementation of
  the BCBS 239 risk-data-aggregation lakehouse pattern Capgemini Risk Data
  Insights and Big-4 BCBS 239 advisory practices recommend G-SIBs build atop
  Databricks Unity Catalog**, on synthetic data — not a vendor-displacement
  product or a regulator-ready evidence layer.

---

## Pre-capture checklist

Before recording, run **all four** to get the workspace into the canonical
state:

```bash
# 1. Reset to clean data
python -m bcbs239_lakehouse.data.synthetic --output data/synthetic --seed 42
make uc-data-upload

# 2. Re-run the live notebooks once for the clean snapshot (optional — only if
#    you want a snapshot_ts in the same minute as the recording)
#    OR: just use the existing T1 snapshot already in fact_dq_scorecard

# 3. Inject defects
make inject-defects        # cleanliness=0.7
make uc-data-upload
make refresh               # writes the T2 snapshot

# 4. Verify
python -c "..." # the two-snapshot diff query above
```

Workspace should now have:

- 100/311/395 clean rows in Bronze (T1) + 100/316/400 dirty rows appended (T2)
- Silver tables holding latest-by-natural-key (the dirty version)
- 2 snapshots in `gold.fact_dq_scorecard` with the visible drift

---

## Time budget

| Capture          | Effort   | Skip if tight on time  |
| ---------------- | -------- | ---------------------- |
| 1. Catalog tree  | 30s      | Never                  |
| 2. Bronze sample | 30s      | Maybe                  |
| 3. Silver schema | 30s      | Maybe                  |
| 4. Drift query   | 1 min    | **Never** — money shot |
| 5. Terminal GIF  | 5-10 min | First if budget < 15m  |

Minimum viable pitch: screenshots 1 + 4 (architecture + drift). Everything
else is supporting evidence.
