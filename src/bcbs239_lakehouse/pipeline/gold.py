"""Gold layer — aggregations + the DQ scorecard mart.

Two marts:

* ``fact_rwa_aggregation`` — Risk-Weighted Asset rollup by
  (entity, exposure_type, as_of_date). RWA = amount_eur * risk_weight.
* ``fact_dq_scorecard`` — one row per (source, dimension, snapshot_ts)
  computed by the scorers in :mod:`bcbs239_lakehouse.quality.dimensions`.
  This is what the Lakeview dashboard binds to in W2.

Both marts are pure Polars derivations of Silver — no external warehouse.
The dbt-databricks Gold marts in ``dbt_project/`` express the same logic
in SQL for the Databricks-runtime path.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl

from bcbs239_lakehouse.pipeline.silver import read_silver_table
from bcbs239_lakehouse.quality.dimensions import (
    DQScore,
    score_accuracy_value_in_range,
    score_completeness,
    score_integrity_dedup,
    score_timeliness,
    utc_now,
)

COMPLETENESS_REQUIRED_FIELDS: dict[str, list[str]] = {
    "counterparty": ["lei", "legal_name", "country_iso2", "sector"],
    "exposure": ["exposure_id", "lei", "amount_eur", "risk_weight", "as_of_date"],
    "collateral": ["collateral_id", "exposure_id", "value_eur", "valuation_date"],
}

NATURAL_KEYS: dict[str, list[str]] = {
    "counterparty": ["lei"],
    "exposure": ["exposure_id"],
    "collateral": ["collateral_id"],
}


def aggregate_rwa(silver_root: Path) -> pl.DataFrame:
    """Aggregate Risk-Weighted Assets by (lei, exposure_type, as_of_date).

    Bad rows (negative amount, invalid risk weight) are still aggregated —
    the resulting figures are wrong on dirty data, which is precisely the
    point: DQ scorecard quantifies the wrongness independently.
    """
    exposure = read_silver_table(silver_root, "exposure")
    return (
        exposure.with_columns(
            (pl.col("amount_eur") * pl.col("risk_weight")).alias("rwa_eur"),
        )
        .group_by(["lei", "exposure_type", "as_of_date"])
        .agg(
            pl.len().alias("exposure_count"),
            pl.sum("amount_eur").alias("total_amount_eur"),
            pl.sum("rwa_eur").alias("total_rwa_eur"),
        )
        .sort(["lei", "exposure_type", "as_of_date"])
    )


def _score_one_silver_table(silver_root: Path, source: str, snapshot_ts: datetime) -> list[DQScore]:
    """Run the 4 BCBS 239 DQ dimensions against one Silver table."""
    df = read_silver_table(silver_root, source)
    rows = df.to_dicts()
    scores: list[DQScore] = []

    # Completeness — required-field non-null check
    scores.append(
        score_completeness(
            rows,
            required_fields=COMPLETENESS_REQUIRED_FIELDS[source],
            source=source,
        )
    )

    # Integrity — natural-key uniqueness
    scores.append(score_integrity_dedup(rows, natural_key=NATURAL_KEYS[source], source=source))

    # Source-specific accuracy + timeliness checks
    if source == "exposure":
        # Accuracy: risk_weight should be in the Basel-permitted range
        scores.append(
            score_accuracy_value_in_range(
                rows, field="risk_weight", min_value=0.0, max_value=1.5, source=source
            )
        )
        # Timeliness: every as_of_date in the snapshot should equal the latest
        as_ofs = [r["as_of_date"] for r in rows if r.get("as_of_date") is not None]
        if as_ofs:
            expected = max(as_ofs)
            scores.append(
                score_timeliness(as_ofs, expected_snapshot=expected, max_lag_days=0, source=source)
            )
    elif source == "collateral":
        # Accuracy: haircut_pct must be in [0, 1]
        scores.append(
            score_accuracy_value_in_range(
                rows, field="haircut_pct", min_value=0.0, max_value=1.0, source=source
            )
        )
        # Timeliness: valuation_date should not be after the latest seen
        valuations = [r["valuation_date"] for r in rows if r.get("valuation_date") is not None]
        if valuations:
            expected = max(valuations)
            scores.append(
                score_timeliness(
                    valuations,
                    expected_snapshot=expected,
                    max_lag_days=180,
                    source=source,
                )
            )
    elif source == "counterparty":
        # Counterparty has no per-snapshot timeliness/accuracy here in v1.
        pass
    return scores


def score_dq_for_silver(silver_root: Path) -> pl.DataFrame:
    """Score the 4 BCBS 239 DQ dimensions across every Silver table."""
    snapshot_ts = utc_now()
    rows: list[dict[str, object]] = []
    for source in ("counterparty", "exposure", "collateral"):
        if not (silver_root / source).exists():
            continue
        for s in _score_one_silver_table(silver_root, source, snapshot_ts):
            rows.append(
                {
                    "snapshot_ts": snapshot_ts,
                    "source": s.source,
                    "dimension": s.dimension,
                    "score": s.score,
                    "sample_size": s.sample_size,
                    "failed_count": s.failed_count,
                }
            )
    return pl.DataFrame(
        rows,
        schema={
            "snapshot_ts": pl.Datetime("us", "UTC"),
            "source": pl.Utf8,
            "dimension": pl.Utf8,
            "score": pl.Float64,
            "sample_size": pl.Int64,
            "failed_count": pl.Int64,
        },
    )


def run_gold(silver_root: Path, gold_root: Path) -> dict[str, int]:
    """Compute Gold marts and persist to ``gold_root``."""
    gold_root.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    if (silver_root / "exposure").exists():
        rwa = aggregate_rwa(silver_root)
        rwa.write_delta(str(gold_root / "fact_rwa_aggregation"), mode="overwrite")
        counts["fact_rwa_aggregation"] = rwa.height

    dq = score_dq_for_silver(silver_root)
    if not dq.is_empty():
        dq.write_delta(str(gold_root / "fact_dq_scorecard"), mode="append")
        counts["fact_dq_scorecard"] = dq.height
    else:
        counts["fact_dq_scorecard"] = 0

    return counts


def read_gold_table(gold_root: Path, table_name: str) -> pl.DataFrame:
    """Read a Gold Delta table back as a Polars DataFrame."""
    table_path = gold_root / table_name
    if not table_path.exists():
        raise FileNotFoundError(f"Gold table not found: {table_path}")
    return pl.read_delta(str(table_path))
