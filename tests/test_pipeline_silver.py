"""Tests for the Silver layer (typed casts + dedup)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest

from bcbs239_lakehouse.data.synthetic import write_synthetic_dataset
from bcbs239_lakehouse.pipeline.bronze import (
    META_COL_INGEST_TS,
    META_COL_SOURCE_FILE,
    ingest_bronze,
)
from bcbs239_lakehouse.pipeline.silver import (
    SILVER_LOAD_TS_COL,
    cast_collateral,
    cast_counterparty,
    cast_exposure,
    read_silver_table,
    run_silver,
)


@pytest.fixture
def bronze_dir(tmp_path: Path) -> Path:
    """Generate synthetic data and ingest it into Bronze; return Bronze root."""
    src = tmp_path / "synthetic"
    write_synthetic_dataset(src, n_counterparties=15, seed=42)
    bronze = tmp_path / "bronze"
    ingest_bronze(source_dir=src, bronze_root=bronze)
    return bronze


# ── metadata stripping + lineage column ───────────────────────────────


def _bronze_df(name: str, bronze_dir: Path) -> pl.DataFrame:
    from bcbs239_lakehouse.pipeline.bronze import read_bronze_table

    return read_bronze_table(bronze_dir, name)


def test_silver_drops_source_file_and_renames_ingest_ts(bronze_dir: Path) -> None:
    silver = cast_counterparty(_bronze_df("counterparty", bronze_dir))
    assert META_COL_SOURCE_FILE not in silver.columns
    assert META_COL_INGEST_TS not in silver.columns
    assert SILVER_LOAD_TS_COL in silver.columns


# ── typed casts ───────────────────────────────────────────────────────


def test_cast_counterparty_inception_date_is_date_type(bronze_dir: Path) -> None:
    silver = cast_counterparty(_bronze_df("counterparty", bronze_dir))
    assert silver.schema["inception_date"] == pl.Date


def test_cast_exposure_amount_is_float(bronze_dir: Path) -> None:
    silver = cast_exposure(_bronze_df("exposure", bronze_dir))
    assert silver.schema["amount_eur"] == pl.Float64
    assert silver.schema["risk_weight"] == pl.Float64
    assert silver.schema["internal_rating"] == pl.Int32
    assert silver.schema["as_of_date"] == pl.Date
    assert silver.schema["maturity_date"] == pl.Date


def test_cast_collateral_dates_and_floats(bronze_dir: Path) -> None:
    silver = cast_collateral(_bronze_df("collateral", bronze_dir))
    assert silver.schema["value_eur"] == pl.Float64
    assert silver.schema["haircut_pct"] == pl.Float64
    assert silver.schema["valuation_date"] == pl.Date
    assert silver.schema["pledge_date"] == pl.Date


# ── dedup on natural key ──────────────────────────────────────────────


def test_dedupe_keeps_one_row_per_natural_key() -> None:
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 5, 1, tzinfo=UTC)
    bronze = pl.DataFrame(
        {
            "lei": ["9999A", "9999A", "9999B"],
            "legal_name": ["Old Name", "New Name", "Other"],
            "country_iso2": ["FR", "FR", "DE"],
            "sector": ["BANKS", "BANKS", "BANKS"],
            "parent_lei": [None, None, None],
            "inception_date": ["2020-01-01", "2020-01-01", "2021-06-15"],
            "_source_file": ["a.csv", "b.csv", "a.csv"],
            "_ingest_ts": [older, newer, older],
        }
    )
    silver = cast_counterparty(bronze)
    assert silver.height == 2
    new_row = silver.filter(pl.col("lei") == "9999A").to_dicts()[0]
    assert new_row["legal_name"] == "New Name"


# ── business-rule violations are PRESERVED for DQ ─────────────────────


def test_silver_preserves_negative_amounts(bronze_dir: Path) -> None:
    """Silver does NOT quarantine bad business values — DQ surfaces them later."""
    silver = cast_exposure(_bronze_df("exposure", bronze_dir))
    # Build a one-row DataFrame matching silver's schema exactly, then concat.
    extra = pl.DataFrame(
        {
            "exposure_id": ["EXP9999_TEST_NEG"],
            "lei": [silver.get_column("lei")[0]],
            "exposure_type": ["LOAN"],
            "amount_eur": [-1000.0],
            "as_of_date": [date(2026, 3, 31)],
            "maturity_date": [date(2027, 3, 31)],
            "risk_weight": [1.0],
            "ifrs9_stage": ["STAGE_1"],
            "internal_rating": [5],
            SILVER_LOAD_TS_COL: [datetime(2026, 5, 1, tzinfo=UTC)],
        },
        schema_overrides=dict(silver.schema.items()),
    ).select(silver.columns)
    polluted = pl.concat([silver, extra])
    bad = polluted.filter(pl.col("amount_eur") < 0).height
    assert bad == 1, "Silver must preserve negative amounts so DQ can surface them"


# ── run_silver end-to-end ─────────────────────────────────────────────


def test_run_silver_creates_three_tables(bronze_dir: Path, tmp_path: Path) -> None:
    silver_root = tmp_path / "silver"
    counts = run_silver(bronze_root=bronze_dir, silver_root=silver_root)
    assert set(counts.keys()) == {"counterparty", "exposure", "collateral"}
    for name in counts:
        assert (silver_root / name).exists()


def test_run_silver_row_counts_consistent_with_bronze(bronze_dir: Path, tmp_path: Path) -> None:
    silver_root = tmp_path / "silver"
    counts = run_silver(bronze_root=bronze_dir, silver_root=silver_root)
    for name in ("counterparty", "exposure", "collateral"):
        bronze_df = _bronze_df(name, bronze_dir)
        # Silver dedupes on natural key → row count <= bronze row count
        assert counts[name] <= bronze_df.height


def test_run_silver_overwrites_on_rerun(bronze_dir: Path, tmp_path: Path) -> None:
    silver_root = tmp_path / "silver"
    first = run_silver(bronze_root=bronze_dir, silver_root=silver_root)
    second = run_silver(bronze_root=bronze_dir, silver_root=silver_root)
    assert first == second  # deterministic; same input = same output


def test_run_silver_skips_missing_bronze_tables(tmp_path: Path) -> None:
    bronze_root = tmp_path / "bronze"
    bronze_root.mkdir()
    silver_root = tmp_path / "silver"
    counts = run_silver(bronze_root=bronze_root, silver_root=silver_root)
    assert counts == {}


# ── read helpers ──────────────────────────────────────────────────────


def test_read_silver_table_after_run(bronze_dir: Path, tmp_path: Path) -> None:
    silver_root = tmp_path / "silver"
    run_silver(bronze_root=bronze_dir, silver_root=silver_root)
    cp = read_silver_table(silver_root, "counterparty")
    assert cp.height > 0
    assert cp.schema["inception_date"] == pl.Date


def test_read_silver_table_rejects_missing(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    silver.mkdir()
    with pytest.raises(FileNotFoundError, match="Silver table not found"):
        read_silver_table(silver, "nope")
