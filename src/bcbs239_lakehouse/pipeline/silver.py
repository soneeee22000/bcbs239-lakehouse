"""Silver layer — typed casts, light cleansing, dedup on natural key.

Silver receives the all-string Bronze and produces strongly-typed tables.
Business-rule violations (negative amount, future maturity, invalid risk
weight) are preserved by design — they are detected and surfaced by the
DQ scorers in :mod:`bcbs239_lakehouse.quality.dimensions` operating on
the Silver outputs. Quarantining bad rows before DQ would hide the
defects the dashboard is meant to expose (PRD Story 3).

Strict invariants Silver does enforce:

* Natural-key uniqueness via dedup, keeping the row with the latest
  ``_ingest_ts`` from Bronze (last-write-wins on the auto-loader log).
* The ``_source_file`` Bronze column is dropped; ``_ingest_ts`` is renamed
  to ``silver_loaded_at`` and retained for lineage.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from bcbs239_lakehouse.pipeline.bronze import (
    META_COL_INGEST_TS,
    META_COL_SOURCE_FILE,
    read_bronze_table,
)

SILVER_LOAD_TS_COL = "silver_loaded_at"


def _strip_bronze_metadata(df: pl.DataFrame) -> pl.DataFrame:
    """Drop ``_source_file``, rename ``_ingest_ts`` → ``silver_loaded_at``."""
    keep = [c for c in df.columns if c != META_COL_SOURCE_FILE]
    out = df.select(keep)
    if META_COL_INGEST_TS in out.columns:
        out = out.rename({META_COL_INGEST_TS: SILVER_LOAD_TS_COL})
    return out


def _dedupe_keep_latest(df: pl.DataFrame, natural_key: list[str]) -> pl.DataFrame:
    """Keep one row per natural key — the one with the highest ``silver_loaded_at``."""
    if not natural_key:
        raise ValueError("natural_key must not be empty")
    if SILVER_LOAD_TS_COL not in df.columns:
        return df.unique(subset=natural_key, keep="last")
    return df.sort(SILVER_LOAD_TS_COL, descending=False).unique(
        subset=natural_key, keep="last", maintain_order=True
    )


def cast_counterparty(bronze_df: pl.DataFrame) -> pl.DataFrame:
    """Cast Bronze counterparty columns to typed Silver schema."""
    df = _strip_bronze_metadata(bronze_df)
    df = df.with_columns(
        pl.col("inception_date").str.strptime(pl.Date, format="%Y-%m-%d", strict=False),
    )
    return _dedupe_keep_latest(df, natural_key=["lei"])


def cast_exposure(bronze_df: pl.DataFrame) -> pl.DataFrame:
    """Cast Bronze exposure columns to typed Silver schema."""
    df = _strip_bronze_metadata(bronze_df)
    df = df.with_columns(
        pl.col("amount_eur").cast(pl.Float64, strict=False),
        pl.col("risk_weight").cast(pl.Float64, strict=False),
        pl.col("internal_rating").cast(pl.Int32, strict=False),
        pl.col("as_of_date").str.strptime(pl.Date, format="%Y-%m-%d", strict=False),
        pl.col("maturity_date").str.strptime(pl.Date, format="%Y-%m-%d", strict=False),
    )
    return _dedupe_keep_latest(df, natural_key=["exposure_id"])


def cast_collateral(bronze_df: pl.DataFrame) -> pl.DataFrame:
    """Cast Bronze collateral columns to typed Silver schema."""
    df = _strip_bronze_metadata(bronze_df)
    df = df.with_columns(
        pl.col("value_eur").cast(pl.Float64, strict=False),
        pl.col("haircut_pct").cast(pl.Float64, strict=False),
        pl.col("valuation_date").str.strptime(pl.Date, format="%Y-%m-%d", strict=False),
        pl.col("pledge_date").str.strptime(pl.Date, format="%Y-%m-%d", strict=False),
    )
    return _dedupe_keep_latest(df, natural_key=["collateral_id"])


SILVER_TRANSFORMS = {
    "counterparty": cast_counterparty,
    "exposure": cast_exposure,
    "collateral": cast_collateral,
}


def run_silver(bronze_root: Path, silver_root: Path) -> dict[str, int]:
    """Read each Bronze table, apply the matching cast, persist to Silver Delta.

    Returns a dict mapping silver table name to row count after dedup.
    """
    silver_root.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for table_name, transform in SILVER_TRANSFORMS.items():
        bronze_table_path = bronze_root / table_name
        if not bronze_table_path.exists():
            continue
        bronze_df = read_bronze_table(bronze_root, table_name)
        silver_df = transform(bronze_df)
        silver_table_path = silver_root / table_name
        silver_df.write_delta(str(silver_table_path), mode="overwrite")
        counts[table_name] = silver_df.height
    return counts


def read_silver_table(silver_root: Path, table_name: str) -> pl.DataFrame:
    """Read a Silver Delta table back as a Polars DataFrame."""
    table_path = silver_root / table_name
    if not table_path.exists():
        raise FileNotFoundError(f"Silver table not found: {table_path}")
    return pl.read_delta(str(table_path))
