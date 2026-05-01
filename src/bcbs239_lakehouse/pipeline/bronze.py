"""Bronze ingestion — raw CSV landing into Delta tables.

The Auto Loader pattern in Databricks tracks new files in a checkpoint
location and ingests each file exactly once. Locally, we replicate that
contract with a tiny ``_ingest_log`` Delta table tracking
``(source_file, table_name, row_count, ingest_ts)``. Re-running ingest
on the same source directory is a no-op — that's the idempotency
guarantee that PRD Story 1 acceptance criteria depends on.

Implementation uses Polars + ``deltalake`` (Rust) — no JVM, no Hadoop
``winutils``, runs identically on Windows / macOS / Linux. The Databricks
notebooks/ path uses native PySpark + Delta; the architecture is the same.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

INGEST_LOG_TABLE = "_ingest_log"
META_COL_SOURCE_FILE = "_source_file"
META_COL_INGEST_TS = "_ingest_ts"


def _ingest_log_path(bronze_root: Path) -> Path:
    return bronze_root / INGEST_LOG_TABLE


def _read_ingested_filenames(bronze_root: Path) -> set[str]:
    """Return the set of source-file names already ingested into Bronze."""
    log_path = _ingest_log_path(bronze_root)
    if not log_path.exists():
        return set()
    log_df = pl.read_delta(str(log_path))
    if log_df.is_empty():
        return set()
    return set(log_df.get_column("source_file").to_list())


def _append_ingest_log(
    bronze_root: Path,
    source_file: str,
    table_name: str,
    row_count: int,
    ingest_ts: datetime,
) -> None:
    log_path = _ingest_log_path(bronze_root)
    record = pl.DataFrame(
        {
            "source_file": [source_file],
            "table_name": [table_name],
            "row_count": [row_count],
            "ingest_ts": [ingest_ts],
        }
    )
    record.write_delta(str(log_path), mode="append")


def ingest_bronze(
    source_dir: Path,
    bronze_root: Path,
    file_pattern: str = "*.csv",
) -> dict[str, int]:
    """Ingest matching CSVs from ``source_dir`` into Bronze Delta tables.

    Each CSV becomes (or appends to) a Delta table named after the file stem
    (``counterparty.csv`` → ``<bronze_root>/counterparty``). Two metadata
    columns (``_source_file``, ``_ingest_ts``) are appended to every row.
    The function is idempotent: files whose names already appear in the
    ingest log are skipped.

    Returns a dict mapping table name to rows ingested in *this run* (zero
    when the file was previously ingested).
    """
    if not source_dir.exists():
        raise FileNotFoundError(f"source_dir does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise NotADirectoryError(f"source_dir is not a directory: {source_dir}")

    bronze_root.mkdir(parents=True, exist_ok=True)
    already_ingested = _read_ingested_filenames(bronze_root)

    counts: dict[str, int] = {}
    for csv_path in sorted(source_dir.glob(file_pattern)):
        if not csv_path.is_file():
            continue
        table_name = csv_path.stem
        if csv_path.name in already_ingested:
            counts[table_name] = 0
            continue

        ingest_ts = datetime.now(tz=UTC)
        # Bronze contract: preserve raw bytes — read every column as Utf8 and let
        # Silver perform the typed cast. infer_schema_length=0 triggers all-string
        # mode; this is what avoids overflow on the 20-digit synthetic LEI.
        df = pl.read_csv(csv_path, infer_schema_length=0)
        df = df.with_columns(
            pl.lit(csv_path.name).alias(META_COL_SOURCE_FILE),
            pl.lit(ingest_ts).alias(META_COL_INGEST_TS),
        )
        table_path = bronze_root / table_name
        df.write_delta(str(table_path), mode="append")
        counts[table_name] = df.height

        _append_ingest_log(
            bronze_root=bronze_root,
            source_file=csv_path.name,
            table_name=table_name,
            row_count=df.height,
            ingest_ts=ingest_ts,
        )
    return counts


def read_bronze_table(bronze_root: Path, table_name: str) -> pl.DataFrame:
    """Read a Bronze Delta table back as a Polars DataFrame."""
    table_path = bronze_root / table_name
    if not table_path.exists():
        raise FileNotFoundError(f"Bronze table not found: {table_path}")
    return pl.read_delta(str(table_path))
