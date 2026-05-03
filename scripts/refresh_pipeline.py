"""Re-run the Bronze→Silver→Gold pipeline against the latest CSVs in the UC volume.

Equivalent of running notebooks/01_bronze.py + 02_silver.py + 03_gold.py but
expressed as Spark SQL against the SQL warehouse, so it's a one-shot Python
call instead of three Chrome 'Run all' clicks. Used during the defect-injection
demo: regenerate dirty CSVs locally → upload via `make uc-data-upload` → run
this script → query gold.fact_dq_scorecard for the new snapshot.

This is NOT a replacement for the notebooks — those remain the canonical
demo artifact. This script is the deterministic, terminal-driven path for
the data-drift loop.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

CATALOG = "bcbs239_lakehouse"
VOLUME = f"/Volumes/{CATALOG}/raw/synthetic"


def main() -> None:
    load_dotenv(dotenv_path=Path(".env"))
    client = WorkspaceClient(
        host=os.environ["DATABRICKS_HOST"],
        token=os.environ["DATABRICKS_TOKEN"],
    )
    warehouse = next(iter(client.warehouses.list()))
    print(f"using warehouse: {warehouse.name} (id={warehouse.id})")

    def run(sql: str, label: str) -> None:
        res = client.statement_execution.execute_statement(
            warehouse_id=warehouse.id, statement=sql, wait_timeout="50s"
        )
        state = str(res.status.state) if res.status else "None"
        print(f"  {label}: {state.split('.')[-1]}")
        if state != "StatementState.SUCCEEDED":
            err = res.status.error.message if res.status and res.status.error else "no detail"
            raise SystemExit(f"FAIL: {label}: {err}")

    print("\n=== BRONZE: append latest CSV contents ===")
    bronze_columns: dict[str, tuple[str, ...]] = {
        "counterparty": (
            "lei",
            "legal_name",
            "country_iso2",
            "sector",
            "parent_lei",
            "inception_date",
        ),
        "exposure": (
            "exposure_id",
            "lei",
            "exposure_type",
            "amount_eur",
            "as_of_date",
            "maturity_date",
            "risk_weight",
            "ifrs9_stage",
            "internal_rating",
        ),
        "collateral": (
            "collateral_id",
            "exposure_id",
            "collateral_type",
            "value_eur",
            "haircut_pct",
            "valuation_date",
            "pledge_date",
        ),
    }
    for table, cols in bronze_columns.items():
        # Bronze contract: every CSV column is preserved as STRING. read_files()
        # auto-infers types (decimals, dates) and adds _rescued_data — cast each
        # column back to STRING and explicitly project past _rescued_data.
        cast_cols = ", ".join(f"CAST({c} AS STRING) AS {c}" for c in cols)
        col_list = ", ".join((*cols, "_source_file", "_ingest_ts"))
        run(
            f"""
            INSERT INTO {CATALOG}.bronze.{table} ({col_list})
            SELECT {cast_cols},
                   '{table}.csv' AS _source_file,
                   current_timestamp() AS _ingest_ts
            FROM read_files('{VOLUME}/{table}.csv', format => 'csv', header => 'true')
            """,
            label=f"bronze.{table} append",
        )

    print("\n=== SILVER: overwrite + dedup keep-latest-by-silver_loaded_at ===")
    run(
        f"""
        CREATE OR REPLACE TABLE {CATALOG}.silver.counterparty AS
        SELECT lei, legal_name, country_iso2, sector, parent_lei,
               CAST(inception_date AS DATE) AS inception_date,
               silver_loaded_at
        FROM (
          SELECT *, row_number() OVER (PARTITION BY lei ORDER BY silver_loaded_at DESC) AS _rn
          FROM (
            SELECT lei, legal_name, country_iso2, sector, parent_lei, inception_date,
                   _ingest_ts AS silver_loaded_at
            FROM {CATALOG}.bronze.counterparty
          )
        ) WHERE _rn = 1
        """,
        label="silver.counterparty",
    )
    run(
        f"""
        CREATE OR REPLACE TABLE {CATALOG}.silver.exposure AS
        SELECT exposure_id, lei, exposure_type,
               CAST(amount_eur AS DOUBLE) AS amount_eur,
               CAST(as_of_date AS DATE) AS as_of_date,
               CAST(maturity_date AS DATE) AS maturity_date,
               CAST(risk_weight AS DOUBLE) AS risk_weight,
               ifrs9_stage,
               CAST(internal_rating AS INT) AS internal_rating,
               silver_loaded_at
        FROM (
          SELECT *, row_number() OVER (PARTITION BY exposure_id ORDER BY silver_loaded_at DESC) AS _rn
          FROM (
            SELECT exposure_id, lei, exposure_type, amount_eur, as_of_date, maturity_date,
                   risk_weight, ifrs9_stage, internal_rating,
                   _ingest_ts AS silver_loaded_at
            FROM {CATALOG}.bronze.exposure
          )
        ) WHERE _rn = 1
        """,
        label="silver.exposure",
    )
    run(
        f"""
        CREATE OR REPLACE TABLE {CATALOG}.silver.collateral AS
        SELECT collateral_id, exposure_id, collateral_type,
               CAST(value_eur AS DOUBLE) AS value_eur,
               CAST(haircut_pct AS DOUBLE) AS haircut_pct,
               CAST(valuation_date AS DATE) AS valuation_date,
               CAST(pledge_date AS DATE) AS pledge_date,
               silver_loaded_at
        FROM (
          SELECT *, row_number() OVER (PARTITION BY collateral_id ORDER BY silver_loaded_at DESC) AS _rn
          FROM (
            SELECT collateral_id, exposure_id, collateral_type, value_eur, haircut_pct,
                   valuation_date, pledge_date,
                   _ingest_ts AS silver_loaded_at
            FROM {CATALOG}.bronze.collateral
          )
        ) WHERE _rn = 1
        """,
        label="silver.collateral",
    )

    print("\n=== GOLD: fact_rwa_aggregation overwrite ===")
    run(
        f"""
        CREATE OR REPLACE TABLE {CATALOG}.gold.fact_rwa_aggregation AS
        SELECT lei, exposure_type, as_of_date,
               count(*) AS exposure_count,
               sum(amount_eur) AS total_amount_eur,
               sum(amount_eur * risk_weight) AS total_rwa_eur
        FROM {CATALOG}.silver.exposure
        GROUP BY lei, exposure_type, as_of_date
        """,
        label="gold.fact_rwa_aggregation",
    )

    print("\n=== GOLD: fact_dq_scorecard append (new snapshot) ===")
    snapshot_ts = datetime.now(tz=UTC).isoformat()
    # Each branch produces a single (source, dimension, score, sample_size, failed_count) row.
    scorecard_sql = f"""
    INSERT INTO {CATALOG}.gold.fact_dq_scorecard
    WITH
      cp AS (SELECT * FROM {CATALOG}.silver.counterparty),
      ex AS (SELECT * FROM {CATALOG}.silver.exposure),
      cl AS (SELECT * FROM {CATALOG}.silver.collateral),
      ex_latest AS (SELECT max(as_of_date) AS d FROM ex),
      cl_latest AS (SELECT max(valuation_date) AS d FROM cl)
    SELECT * FROM (
      -- counterparty: completeness (lei, legal_name, country_iso2, sector)
      SELECT cast('{snapshot_ts}' AS TIMESTAMP) AS snapshot_ts,
             'counterparty' AS source, 'completeness' AS dimension,
             1.0 - (sum(CASE WHEN lei IS NULL OR legal_name IS NULL OR country_iso2 IS NULL OR sector IS NULL THEN 1 ELSE 0 END) / cast(count(*) AS DOUBLE)) AS score,
             cast(count(*) AS BIGINT) AS sample_size,
             cast(sum(CASE WHEN lei IS NULL OR legal_name IS NULL OR country_iso2 IS NULL OR sector IS NULL THEN 1 ELSE 0 END) AS BIGINT) AS failed_count
      FROM cp
      UNION ALL
      -- counterparty: integrity (lei distinct = total)
      SELECT cast('{snapshot_ts}' AS TIMESTAMP), 'counterparty', 'integrity',
             cast(count(DISTINCT lei) AS DOUBLE) / cast(count(*) AS DOUBLE),
             cast(count(*) AS BIGINT),
             cast(count(*) - count(DISTINCT lei) AS BIGINT)
      FROM cp
      UNION ALL
      -- exposure: completeness
      SELECT cast('{snapshot_ts}' AS TIMESTAMP), 'exposure', 'completeness',
             1.0 - (sum(CASE WHEN exposure_id IS NULL OR lei IS NULL OR amount_eur IS NULL OR risk_weight IS NULL OR as_of_date IS NULL THEN 1 ELSE 0 END) / cast(count(*) AS DOUBLE)),
             cast(count(*) AS BIGINT),
             cast(sum(CASE WHEN exposure_id IS NULL OR lei IS NULL OR amount_eur IS NULL OR risk_weight IS NULL OR as_of_date IS NULL THEN 1 ELSE 0 END) AS BIGINT)
      FROM ex
      UNION ALL
      -- exposure: integrity
      SELECT cast('{snapshot_ts}' AS TIMESTAMP), 'exposure', 'integrity',
             cast(count(DISTINCT exposure_id) AS DOUBLE) / cast(count(*) AS DOUBLE),
             cast(count(*) AS BIGINT),
             cast(count(*) - count(DISTINCT exposure_id) AS BIGINT)
      FROM ex
      UNION ALL
      -- exposure: accuracy (risk_weight in [0, 1.5])
      SELECT cast('{snapshot_ts}' AS TIMESTAMP), 'exposure', 'accuracy',
             1.0 - (sum(CASE WHEN risk_weight < 0 OR risk_weight > 1.5 THEN 1 ELSE 0 END) / cast(count(*) AS DOUBLE)),
             cast(count(*) AS BIGINT),
             cast(sum(CASE WHEN risk_weight < 0 OR risk_weight > 1.5 THEN 1 ELSE 0 END) AS BIGINT)
      FROM ex
      UNION ALL
      -- exposure: timeliness (as_of_date matches latest)
      SELECT cast('{snapshot_ts}' AS TIMESTAMP), 'exposure', 'timeliness',
             1.0 - (sum(CASE WHEN as_of_date <> (SELECT d FROM ex_latest) THEN 1 ELSE 0 END) / cast(count(*) AS DOUBLE)),
             cast(count(*) AS BIGINT),
             cast(sum(CASE WHEN as_of_date <> (SELECT d FROM ex_latest) THEN 1 ELSE 0 END) AS BIGINT)
      FROM ex
      UNION ALL
      -- collateral: completeness
      SELECT cast('{snapshot_ts}' AS TIMESTAMP), 'collateral', 'completeness',
             1.0 - (sum(CASE WHEN collateral_id IS NULL OR exposure_id IS NULL OR value_eur IS NULL OR valuation_date IS NULL THEN 1 ELSE 0 END) / cast(count(*) AS DOUBLE)),
             cast(count(*) AS BIGINT),
             cast(sum(CASE WHEN collateral_id IS NULL OR exposure_id IS NULL OR value_eur IS NULL OR valuation_date IS NULL THEN 1 ELSE 0 END) AS BIGINT)
      FROM cl
      UNION ALL
      -- collateral: integrity
      SELECT cast('{snapshot_ts}' AS TIMESTAMP), 'collateral', 'integrity',
             cast(count(DISTINCT collateral_id) AS DOUBLE) / cast(count(*) AS DOUBLE),
             cast(count(*) AS BIGINT),
             cast(count(*) - count(DISTINCT collateral_id) AS BIGINT)
      FROM cl
      UNION ALL
      -- collateral: accuracy (haircut_pct in [0, 1])
      SELECT cast('{snapshot_ts}' AS TIMESTAMP), 'collateral', 'accuracy',
             1.0 - (sum(CASE WHEN haircut_pct < 0 OR haircut_pct > 1 THEN 1 ELSE 0 END) / cast(count(*) AS DOUBLE)),
             cast(count(*) AS BIGINT),
             cast(sum(CASE WHEN haircut_pct < 0 OR haircut_pct > 1 THEN 1 ELSE 0 END) AS BIGINT)
      FROM cl
      UNION ALL
      -- collateral: timeliness (valuation within 180d of latest)
      SELECT cast('{snapshot_ts}' AS TIMESTAMP), 'collateral', 'timeliness',
             1.0 - (sum(CASE WHEN datediff((SELECT d FROM cl_latest), valuation_date) > 180 THEN 1 ELSE 0 END) / cast(count(*) AS DOUBLE)),
             cast(count(*) AS BIGINT),
             cast(sum(CASE WHEN datediff((SELECT d FROM cl_latest), valuation_date) > 180 THEN 1 ELSE 0 END) AS BIGINT)
      FROM cl
    )
    """
    run(scorecard_sql, label="gold.fact_dq_scorecard")
    print(f"\nnew scorecard snapshot_ts: {snapshot_ts}")


if __name__ == "__main__":
    main()
