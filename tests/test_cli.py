"""Tests for the demo orchestrator CLI."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from bcbs239_lakehouse.cli import _format_dq_summary, main, run_demo
from bcbs239_lakehouse.pipeline.gold import read_gold_table


def test_run_demo_clean_produces_high_dq_scores(tmp_path: Path) -> None:
    counts = run_demo(
        warehouse_root=tmp_path / "warehouse",
        synthetic_dir=tmp_path / "synthetic",
        n_counterparties=20,
        seed=42,
        cleanliness=1.0,
    )
    assert counts["bronze"]["counterparty"] == 20
    assert counts["silver"]["counterparty"] == 20
    dq = read_gold_table(tmp_path / "warehouse" / "gold", "fact_dq_scorecard")
    assert dq.height > 0
    assert (dq.get_column("score") >= 0.99).all()


def test_run_demo_dirty_drops_dq_scores(tmp_path: Path) -> None:
    """PRD Story 3: dirty data must show measurable drop in scorecards."""
    counts = run_demo(
        warehouse_root=tmp_path / "warehouse",
        synthetic_dir=tmp_path / "synthetic",
        n_counterparties=50,
        seed=42,
        cleanliness=0.5,
    )
    assert counts["gold"]["fact_dq_scorecard"] > 0
    dq = read_gold_table(tmp_path / "warehouse" / "gold", "fact_dq_scorecard")
    assert (dq.get_column("score") < 0.95).any(), (
        "dirty pipeline should produce at least one degraded score"
    )


def test_main_clean_exits_zero(tmp_path: Path) -> None:
    exit_code = main(
        [
            "--root",
            str(tmp_path / "warehouse"),
            "--synthetic-dir",
            str(tmp_path / "synthetic"),
            "--counterparties",
            "10",
            "--seed",
            "42",
        ]
    )
    assert exit_code == 0


def test_main_inject_defects_exits_zero(tmp_path: Path) -> None:
    exit_code = main(
        [
            "--root",
            str(tmp_path / "warehouse"),
            "--synthetic-dir",
            str(tmp_path / "synthetic"),
            "--counterparties",
            "20",
            "--seed",
            "42",
            "--inject-defects",
        ]
    )
    assert exit_code == 0


def test_format_dq_summary_handles_empty() -> None:
    empty = pl.DataFrame(
        schema={
            "snapshot_ts": pl.Datetime("us", "UTC"),
            "source": pl.Utf8,
            "dimension": pl.Utf8,
            "score": pl.Float64,
            "sample_size": pl.Int64,
            "failed_count": pl.Int64,
        }
    )
    summary = _format_dq_summary(empty)
    assert "no DQ scorecard rows" in summary
