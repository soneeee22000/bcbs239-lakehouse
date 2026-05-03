# Deploy — bcbs239-lakehouse on Databricks Free Edition

End-to-end walkthrough for running the reference implementation against a real
Databricks workspace on **Free Edition** (the 2025+ replacement for Community
Edition). Everything is reproducible from a clean account in ~20 minutes,
using only synthetic data.

> **Scope reminder.** This is a portfolio reference implementation of the BCBS
> 239 risk-data-aggregation lakehouse pattern Capgemini Risk Data Insights and
> Big-4 BCBS 239 advisory practices recommend G-SIBs build atop Databricks
> Unity Catalog. Synthetic data only — every numeric claim in the demo is on
> synthetic data.

---

## 0. What this deploys

```
bcbs239_lakehouse                       (UC catalog)
├── bronze                              (schema)
│   ├── counterparty                    (Delta — written by 01_bronze.py)
│   ├── exposure
│   └── collateral
├── silver                              (schema — typed casts + dedup)
├── gold                                (schema)
│   ├── fact_rwa_aggregation            (Delta — written by 03_gold.py)
│   └── fact_dq_scorecard               (Delta — 4 BCBS 239 DQ dimensions)
└── raw                                 (schema — landing zone)
    └── synthetic                       (managed volume — CSV uploads)
```

Plus, optionally in Weekend 2: a Lakeview dashboard bound to
`gold.fact_dq_scorecard`.

---

## 1. Prerequisites

- A Databricks Free Edition account
  ([sign-up](https://www.databricks.com/learn/free-edition))
- Local `uv sync` (run once: `make setup`)
- `.env` populated with workspace host + PAT (see §2)

Free Edition gives you Unity Catalog, SQL warehouses, Lakeview, and notebooks
without a credit card. The
[official limitations page](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)
documents the trade-offs (no jobs API, smaller compute, no Genie unless added).

---

## 2. Configure credentials

Populate `.env` from `.env.example`:

```dotenv
DATABRICKS_HOST=https://dbc-xxxxxxxx-yyyy.cloud.databricks.com
DATABRICKS_TOKEN=dapi...
DATABRICKS_CATALOG=bcbs239_lakehouse
DATABRICKS_SCHEMA_BRONZE=bronze
DATABRICKS_SCHEMA_SILVER=silver
DATABRICKS_SCHEMA_GOLD=gold
```

- `DATABRICKS_HOST` — the workspace URL shown in your browser after sign-in
  (the `dbc-xxxxxxxx-yyyy.cloud.databricks.com` form, **not**
  `community.cloud.databricks.com`).
- `DATABRICKS_TOKEN` — generate via **User Settings → Developer → Access
  tokens → Generate new token**. Recommended:
  - Comment: `bcbs239-lakehouse`
  - Lifetime: 90 days
  - Scope: `Other APIs` → `all-apis` (Free Edition tokens cover everything you
    need for this demo)

Sanity-check the credentials:

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
  -H "Authorization: Bearer $DATABRICKS_TOKEN" \
  "$DATABRICKS_HOST/api/2.0/preview/scim/v2/Me"
# expected: HTTP 200
```

`.env` is gitignored at `.gitignore:52`. Never commit it.

---

## 3. Provision Unity Catalog (catalog + schemas + volume)

```bash
make uc-provision
```

This calls `python -m bcbs239_lakehouse.databricks.cli provision`, which is
**idempotent** — re-running on a provisioned workspace prints `exists` for
each resource and exits zero.

Expected output on a fresh workspace:

```
catalog  bcbs239_lakehouse: created
schema   bcbs239_lakehouse.bronze: created
schema   bcbs239_lakehouse.silver: created
schema   bcbs239_lakehouse.gold: created
schema   bcbs239_lakehouse.raw: created
volume   bcbs239_lakehouse.raw.synthetic: created
```

### Free Edition gotcha — Default Storage catalogs

If `make uc-provision` prints:

```
[free-edition] catalog 'bcbs239_lakehouse' could not be auto-created.
  Reason: Free Edition / Default Storage requires the first catalog to be
  created via the UI.
```

That's the
[Free Edition Default-Storage constraint](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations) —
the SDK can't create the first catalog because the metastore has no managed
storage root. Fix:

1. Open **Catalog** in the left nav
2. Click **Create catalog**
3. Name: `bcbs239_lakehouse`
4. Storage: leave **Use Default Storage** selected
5. Click **Create**

Then re-run `make uc-provision`. The catalog will now exist (idempotent skip);
schemas + volume creation proceeds.

---

## 4. Generate synthetic CSVs locally

```bash
make synthetic
```

Writes deterministic counterparty / exposure / collateral CSVs to
`data/synthetic/` (gitignored, regenerable; LEI prefix `9999` so they're
obvious fakes).

---

## 5. Upload CSVs to the UC volume

The Bronze notebook reads from `/Volumes/bcbs239_lakehouse/raw/synthetic/`.
Upload the three CSVs there:

1. Open **Catalog → bcbs239_lakehouse → raw → synthetic** (volume)
2. Click **Upload to this volume**
3. Drag in `data/synthetic/counterparty.csv`,
   `data/synthetic/exposure.csv`, `data/synthetic/collateral.csv`
4. Confirm; you should see all three files in the volume listing

> Auto-upload via SDK lands as `make uc-data-upload` in Weekend 2 (uses
> `WorkspaceClient.files.upload`). For the V1 demo, the manual drag-and-drop
> takes ~30 seconds.

---

## 6. Import the medallion notebooks

The three PySpark notebooks are committed at:

```
notebooks/01_bronze.py
notebooks/02_silver.py
notebooks/03_gold.py
```

These are Databricks-source-format files (`# Databricks notebook source` magic
header), so they import cleanly into a workspace.

1. In the workspace, open **Workspace → your home folder → New folder →
   bcbs239-lakehouse**
2. Click **Import** in the folder
3. Drag in `notebooks/01_bronze.py` → confirm import (Databricks recognises
   the magic header and treats it as a Python notebook)
4. Repeat for `02_silver.py`, `03_gold.py`

---

## 7. Run the notebooks in order

Free Edition uses serverless compute by default — no cluster setup needed.

1. Open `01_bronze.py` → click **Run all**.
   Expected output: `OK bcbs239_lakehouse.bronze.counterparty: <N> rows`
   for each of the three Bronze tables.
2. Open `02_silver.py` → **Run all**.
   Each cell prints `silver.<table>: <N> rows`.
3. Open `03_gold.py` → **Run all**.
   The final cell `display()`s the DQ scorecard with one row per
   `(source, dimension)` combination — completeness / integrity / accuracy /
   timeliness for each of `counterparty`, `exposure`, `collateral`.

Total runtime on Free Edition serverless: ~3-5 minutes for all three
notebooks on the default 100-counterparty / 500-exposure dataset.

---

## 8. Verify

In **SQL Editor** or a notebook cell:

```sql
SELECT count(*) FROM bcbs239_lakehouse.bronze.counterparty;
SELECT count(*) FROM bcbs239_lakehouse.silver.exposure;
SELECT * FROM bcbs239_lakehouse.gold.fact_dq_scorecard
ORDER BY snapshot_ts DESC, source, dimension
LIMIT 12;
```

You should see 4 rows per source × 3 sources = 12 scorecard rows for the
latest snapshot, with `score` between 0.0 and 1.0.

---

## 9. Publish the Lakeview dashboard

```bash
make lakeview-provision
```

Calls `python -m bcbs239_lakehouse.databricks.cli lakeview` which:

1. Discovers the workspace's SQL warehouse (Free Edition ships one by default
   named "Serverless Starter Warehouse").
2. Reads `src/bcbs239_lakehouse/databricks/dashboards/dq_scorecard.json`.
3. Calls `LakeviewPublisher.publish()` — creates a new "BCBS 239 DQ Scorecard"
   dashboard if absent, or updates the existing one.

Output:

```
dashboard created: 'BCBS 239 DQ Scorecard' (id=01f146..., warehouse=53a002c7...)
```

Dashboard URL pattern: `https://{host}/sql/dashboardsv3/{dashboard_id}`.

### Known limitation — widget visualizations

The bundled JSON spec round-trips through the SDK correctly (datasets, page,
widget skeletons all stored), but Lakeview's current widget-rendering format
is more involved than the spec captures — when you open the dashboard for the
first time, you'll see two empty widget cells with "Describe the
visualization you want to create…" prompts.

To finish populating them (~60 seconds, one-time):

1. Click the first widget cell → "Visualizations" panel on the right →
   choose **Table**, drag `source`, `dimension`, `score`, `sample_size`,
   `failed_count` from the `dq_scorecard_latest` dataset onto the columns
   shelf, set `score` format to `0.0%`.
2. Click the second cell → choose **Line chart** → x: `snapshot_ts`,
   y: `score`, color: `source_dimension` from the `dq_scorecard_trend`
   dataset.
3. Click **Publish** in the top-right.

Re-running `make lakeview-provision` after the manual configuration will
update the dashboard in place (idempotent), preserving the manual widget
config because the publisher doesn't overwrite layout fields it doesn't
explicitly set.

A future-pass JSON-spec rev that auto-renders the widgets is left as a
follow-up; the SQL-Editor-driven money shot in section 10 is sufficient
for the recruiter pitch on its own.

---

## 10. Inject defects → watch the scorecard react

Demonstrates that the DQ scorecard responds to real data quality drift
(PRD Story 3). Three commands:

```bash
make inject-defects        # regenerate synthetic CSVs with cleanliness=0.7
make uc-data-upload        # push dirty CSVs to /Volumes/.../raw/synthetic/
make refresh               # Bronze append + Silver overwrite + Gold append-snapshot
```

The third command runs `scripts/refresh_pipeline.py` — the SQL-warehouse
equivalent of running notebooks 01→02→03 sequentially, but as a one-shot
Python script for the demo loop. ~150 lines of Spark SQL via the Statement
Execution API.

After `make refresh`, query both snapshots side-by-side:

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
       MAX(CASE WHEN label = 'T2_dirty' THEN ROUND(score, 4) END) AS T2_dirty
FROM labeled GROUP BY source, dimension ORDER BY source, dimension;
```

Expected: `collateral.timeliness` drops `1.00 → 0.11`, `exposure.accuracy`
drops `1.00 → 0.91`. See [`DEMO-SCRIPT.md`](DEMO-SCRIPT.md) for the full
capture order.

To restore a clean state:

```bash
python -m bcbs239_lakehouse.data.synthetic --output data/synthetic --seed 42
make uc-data-upload
make refresh
```

---

## 11. Teardown / cost

- Free Edition is, well, free — no billing to wind down
- To wipe the project state on the workspace, in **Catalog Explorer** drop:
  - `bcbs239_lakehouse.raw.synthetic` (volume)
  - `bcbs239_lakehouse.{bronze,silver,gold,raw}` (schemas)
  - `bcbs239_lakehouse` (catalog)
- PAT can be revoked at **User Settings → Developer → Access tokens**
- `make uc-teardown` is intentionally **not** automated — destructive UC
  operations should be a deliberate human click on this project

---

## Troubleshooting

| Symptom                                                                             | Cause                                        | Fix                                                                             |
| ----------------------------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------- |
| `make uc-provision` exits with `[free-edition] catalog ...`                         | Default Storage requires UI catalog creation | §3 — create the catalog via Catalog Explorer, then re-run                       |
| `HTTP 401` from the SCIM check                                                      | PAT expired or wrong workspace               | Re-issue PAT; double-check `DATABRICKS_HOST` matches the post-login URL         |
| `01_bronze.py` fails: `Path /Volumes/.../synthetic/counterparty.csv does not exist` | CSVs not uploaded yet                        | §5 — upload the three CSVs to the volume                                        |
| Bronze tables empty after `01_bronze.py`                                            | Volume path mismatch                         | Check `RAW_VOLUME` in `01_bronze.py` matches `bcbs239_lakehouse.raw.synthetic`  |
| `02_silver.py` errors on `to_date`                                                  | Bronze ingest skipped a column               | Re-run `01_bronze.py`; ensure `_ingest_ts` and `_source_file` cols are present  |
| `03_gold.py` final `display()` shows zero rows                                      | Snapshot timestamp matched no data           | The scorecard appends per-run; check `snapshot_ts` is the most recent           |
| Notebooks won't run — no compute                                                    | Serverless quota hit on Free Edition         | Wait a few minutes; Free Edition serverless throttles on burst, not concurrency |

---

## Why this matters

The whole point of running this on a real workspace (rather than just locally
via `make demo`) is to capture the screenshot / Lakeview GIF that's part of
the recruiter pitch — `Bronze → Silver → Gold` writing real Delta tables in
real Unity Catalog with real lineage, not a SQLite mock. Every step above
takes ≤ 5 minutes; the full first-run is 20 minutes.

After the first deploy, the loop tightens: edit code locally → push → import
notebook → re-run. The library code at `src/bcbs239_lakehouse/` is
platform-agnostic (Polars + delta-rs); the Databricks-specific glue is
isolated in `src/bcbs239_lakehouse/databricks/` and `notebooks/`. Mapping to
a Snowflake stack is documented in [`PORTABILITY.md`](PORTABILITY.md).
