"""Tests for Bronze ingestion (Polars + deltalake-rs)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from bcbs239_lakehouse.data.synthetic import write_synthetic_dataset
from bcbs239_lakehouse.pipeline.bronze import (
    INGEST_LOG_TABLE,
    META_COL_INGEST_TS,
    META_COL_SOURCE_FILE,
    ingest_bronze,
    read_bronze_table,
)


@pytest.fixture
def synthetic_source(tmp_path: Path) -> Path:
    """Generate a small synthetic dataset and return its path."""
    src = tmp_path / "synthetic"
    write_synthetic_dataset(src, n_counterparties=10, seed=42)
    return src


def test_ingest_bronze_creates_one_table_per_csv(synthetic_source: Path, tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    counts = ingest_bronze(source_dir=synthetic_source, bronze_root=bronze)
    assert set(counts.keys()) == {"counterparty", "exposure", "collateral"}
    assert counts["counterparty"] == 10
    assert counts["exposure"] > 0
    assert counts["collateral"] > 0
    for name in ("counterparty", "exposure", "collateral"):
        assert (bronze / name).exists(), f"Bronze table {name} not created"


def test_ingest_bronze_appends_metadata_columns(synthetic_source: Path, tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    ingest_bronze(source_dir=synthetic_source, bronze_root=bronze)
    cp = read_bronze_table(bronze, "counterparty")
    assert META_COL_SOURCE_FILE in cp.columns
    assert META_COL_INGEST_TS in cp.columns
    assert cp.get_column(META_COL_SOURCE_FILE).unique().to_list() == ["counterparty.csv"]


def test_ingest_bronze_is_idempotent(synthetic_source: Path, tmp_path: Path) -> None:
    """Re-running ingest on the same files is a no-op (the auto-loader contract)."""
    bronze = tmp_path / "bronze"
    first = ingest_bronze(source_dir=synthetic_source, bronze_root=bronze)
    second = ingest_bronze(source_dir=synthetic_source, bronze_root=bronze)
    assert all(v > 0 for v in first.values())
    assert all(v == 0 for v in second.values()), f"second ingest should be a no-op, got {second}"
    # Row counts in Bronze must equal first-run totals (no double-write)
    cp = read_bronze_table(bronze, "counterparty")
    assert cp.height == first["counterparty"]


def test_ingest_bronze_writes_ingest_log(synthetic_source: Path, tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    ingest_bronze(source_dir=synthetic_source, bronze_root=bronze)
    log_path = bronze / INGEST_LOG_TABLE
    assert log_path.exists()
    log = pl.read_delta(str(log_path))
    expected_files = {"counterparty.csv", "exposure.csv", "collateral.csv"}
    assert set(log.get_column("source_file").to_list()) == expected_files
    assert log.get_column("row_count").sum() > 0


def test_ingest_bronze_picks_up_new_file_on_second_run(
    synthetic_source: Path, tmp_path: Path
) -> None:
    bronze = tmp_path / "bronze"
    ingest_bronze(source_dir=synthetic_source, bronze_root=bronze)
    # Drop a new file into the source dir
    new_file = synthetic_source / "extra.csv"
    new_file.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    second = ingest_bronze(source_dir=synthetic_source, bronze_root=bronze)
    assert second["extra"] == 2
    assert second["counterparty"] == 0  # already ingested


def test_ingest_bronze_rejects_missing_source_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="source_dir does not exist"):
        ingest_bronze(source_dir=tmp_path / "nope", bronze_root=tmp_path / "bronze")


def test_ingest_bronze_rejects_file_as_source(tmp_path: Path) -> None:
    not_a_dir = tmp_path / "actually_a_file.txt"
    not_a_dir.write_text("hello", encoding="utf-8")
    with pytest.raises(NotADirectoryError, match="is not a directory"):
        ingest_bronze(source_dir=not_a_dir, bronze_root=tmp_path / "bronze")


def test_ingest_bronze_empty_dir_returns_empty_counts(tmp_path: Path) -> None:
    src = tmp_path / "empty"
    src.mkdir()
    counts = ingest_bronze(source_dir=src, bronze_root=tmp_path / "bronze")
    assert counts == {}


def test_read_bronze_table_rejects_missing_table(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    with pytest.raises(FileNotFoundError, match="Bronze table not found"):
        read_bronze_table(bronze, "nonexistent")


def test_ingest_bronze_round_trip_preserves_row_count(
    synthetic_source: Path, tmp_path: Path
) -> None:
    """Number of rows landed in Bronze == number of rows in source CSV."""
    bronze = tmp_path / "bronze"
    counts = ingest_bronze(source_dir=synthetic_source, bronze_root=bronze)
    for name in ("counterparty", "exposure", "collateral"):
        # infer_schema_length=0 mirrors Bronze's all-string read; otherwise the
        # 20-digit synthetic LEI overflows Polars' Int64 inference.
        source_rows = pl.read_csv(synthetic_source / f"{name}.csv", infer_schema_length=0).height
        bronze_rows = read_bronze_table(bronze, name).height
        assert bronze_rows == source_rows == counts[name], (
            f"row-count mismatch for {name}: source={source_rows} "
            f"bronze={bronze_rows} returned={counts[name]}"
        )
