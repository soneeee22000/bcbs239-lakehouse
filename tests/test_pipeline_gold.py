"""Tests for the Gold layer (RWA aggregation + DQ scorecard mart)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from bcbs239_lakehouse.data.synthetic import write_synthetic_dataset
from bcbs239_lakehouse.pipeline.bronze import ingest_bronze
from bcbs239_lakehouse.pipeline.gold import (
    aggregate_rwa,
    read_gold_table,
    run_gold,
    score_dq_for_silver,
)
from bcbs239_lakehouse.pipeline.silver import run_silver


@pytest.fixture
def silver_dir_clean(tmp_path: Path) -> Path:
    src = tmp_path / "synthetic"
    write_synthetic_dataset(src, n_counterparties=20, seed=42, cleanliness=1.0)
    bronze = tmp_path / "bronze"
    ingest_bronze(source_dir=src, bronze_root=bronze)
    silver = tmp_path / "silver"
    run_silver(bronze_root=bronze, silver_root=silver)
    return silver


@pytest.fixture
def silver_dir_dirty(tmp_path: Path) -> Path:
    src = tmp_path / "synthetic"
    write_synthetic_dataset(src, n_counterparties=50, seed=42, cleanliness=0.5)
    bronze = tmp_path / "bronze"
    ingest_bronze(source_dir=src, bronze_root=bronze)
    silver = tmp_path / "silver"
    run_silver(bronze_root=bronze, silver_root=silver)
    return silver


# ── RWA aggregation ───────────────────────────────────────────────────


def test_aggregate_rwa_returns_one_row_per_grouping(silver_dir_clean: Path) -> None:
    rwa = aggregate_rwa(silver_dir_clean)
    assert rwa.height > 0
    # Grouping = (lei, exposure_type, as_of_date) so every (l, t, d) is unique
    n_unique = rwa.unique(subset=["lei", "exposure_type", "as_of_date"]).height
    assert n_unique == rwa.height


def test_aggregate_rwa_columns(silver_dir_clean: Path) -> None:
    rwa = aggregate_rwa(silver_dir_clean)
    assert set(rwa.columns) == {
        "lei",
        "exposure_type",
        "as_of_date",
        "exposure_count",
        "total_amount_eur",
        "total_rwa_eur",
    }


def test_aggregate_rwa_clean_data_all_rwa_non_negative(silver_dir_clean: Path) -> None:
    rwa = aggregate_rwa(silver_dir_clean)
    assert (rwa.get_column("total_rwa_eur") >= 0).all()


def test_aggregate_rwa_dirty_data_includes_negative_rwa(silver_dir_dirty: Path) -> None:
    """Negative-amount or negative-weight rows from dirty data flow through."""
    rwa = aggregate_rwa(silver_dir_dirty)
    has_negative = (rwa.get_column("total_rwa_eur") < 0).any()
    assert has_negative, "dirty data should produce at least one negative-RWA aggregation"


# ── DQ scorecard ──────────────────────────────────────────────────────


def test_score_dq_for_clean_silver_has_high_scores(silver_dir_clean: Path) -> None:
    dq = score_dq_for_silver(silver_dir_clean)
    assert dq.height > 0
    # Every dimension on clean data should score >= 0.99
    for row in dq.iter_rows(named=True):
        assert row["score"] >= 0.99, (
            f"clean data scored {row['score']} on {row['source']}/{row['dimension']}"
        )


def test_score_dq_for_dirty_silver_has_low_accuracy(silver_dir_dirty: Path) -> None:
    """Dirty data must produce visibly degraded accuracy on exposure or completeness somewhere."""
    dq = score_dq_for_silver(silver_dir_dirty)
    accuracy = dq.filter(pl.col("dimension") == "accuracy")
    assert accuracy.height > 0
    # At least one accuracy score should drop below 0.95
    assert (accuracy.get_column("score") < 0.95).any(), (
        f"dirty data should produce visibly degraded accuracy; got {accuracy.to_dicts()}"
    )


def test_score_dq_emits_all_4_dimensions_for_exposure(silver_dir_clean: Path) -> None:
    dq = score_dq_for_silver(silver_dir_clean)
    exposure_dims = set(dq.filter(pl.col("source") == "exposure").get_column("dimension").to_list())
    assert {"completeness", "integrity", "accuracy", "timeliness"} <= exposure_dims


# ── run_gold end-to-end ───────────────────────────────────────────────


def test_run_gold_creates_two_marts(silver_dir_clean: Path, tmp_path: Path) -> None:
    gold = tmp_path / "gold"
    counts = run_gold(silver_dir_clean, gold)
    assert (gold / "fact_rwa_aggregation").exists()
    assert (gold / "fact_dq_scorecard").exists()
    assert counts["fact_rwa_aggregation"] > 0
    assert counts["fact_dq_scorecard"] > 0


def test_run_gold_dq_appends_on_rerun(silver_dir_clean: Path, tmp_path: Path) -> None:
    """fact_dq_scorecard appends each run; fact_rwa overwrites."""
    gold = tmp_path / "gold"
    first = run_gold(silver_dir_clean, gold)
    second = run_gold(silver_dir_clean, gold)
    dq = read_gold_table(gold, "fact_dq_scorecard")
    rwa = read_gold_table(gold, "fact_rwa_aggregation")
    assert dq.height == first["fact_dq_scorecard"] + second["fact_dq_scorecard"]
    assert rwa.height == first["fact_rwa_aggregation"]  # overwrite


def test_read_gold_table_rejects_missing(tmp_path: Path) -> None:
    gold = tmp_path / "gold"
    gold.mkdir()
    with pytest.raises(FileNotFoundError, match="Gold table not found"):
        read_gold_table(gold, "nope")
