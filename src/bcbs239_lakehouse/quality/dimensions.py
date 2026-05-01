"""Data-quality dimension scorers — the 4 data-engineerable BCBS 239 principles.

Pure functions over ``list[dict]`` row sets; no Spark, no Databricks, no I/O.
Bronze/Silver/Gold notebooks call these scorers and persist the
:class:`DQScore` results into the ``fact_dq_scorecard`` Gold table.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

VALID_DIMENSIONS = ("completeness", "accuracy", "timeliness", "integrity")


@dataclass(frozen=True)
class DQScore:
    """One DQ measurement for one source on one snapshot date."""

    dimension: str
    source: str
    score: float
    sample_size: int
    failed_count: int

    def __post_init__(self) -> None:
        if self.dimension not in VALID_DIMENSIONS:
            raise ValueError(f"dimension must be one of {VALID_DIMENSIONS}, got {self.dimension!r}")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be in [0, 1], got {self.score}")
        if self.sample_size < 0 or self.failed_count < 0:
            raise ValueError("sample_size and failed_count must be non-negative")
        if self.failed_count > self.sample_size:
            raise ValueError("failed_count cannot exceed sample_size")


def score_completeness(
    rows: Iterable[dict[str, object]],
    required_fields: list[str],
    source: str,
) -> DQScore:
    """Score completeness as 1 - (rows with any null required field) / total rows."""
    if not required_fields:
        raise ValueError("required_fields must not be empty")
    rows_list = list(rows)
    sample = len(rows_list)
    if sample == 0:
        return DQScore(
            dimension="completeness", source=source, score=1.0, sample_size=0, failed_count=0
        )
    failed = sum(
        1 for row in rows_list if any(row.get(field) in (None, "") for field in required_fields)
    )
    return DQScore(
        dimension="completeness",
        source=source,
        score=1.0 - failed / sample,
        sample_size=sample,
        failed_count=failed,
    )


def score_timeliness(
    snapshots: Iterable[date],
    expected_snapshot: date,
    max_lag_days: int,
    source: str,
) -> DQScore:
    """Score timeliness as fraction of snapshots within ``max_lag_days`` of expected."""
    if max_lag_days < 0:
        raise ValueError("max_lag_days must be non-negative")
    snapshot_list = list(snapshots)
    sample = len(snapshot_list)
    if sample == 0:
        return DQScore(
            dimension="timeliness", source=source, score=1.0, sample_size=0, failed_count=0
        )
    failed = sum(1 for snap in snapshot_list if abs((expected_snapshot - snap).days) > max_lag_days)
    return DQScore(
        dimension="timeliness",
        source=source,
        score=1.0 - failed / sample,
        sample_size=sample,
        failed_count=failed,
    )


def score_integrity_dedup(
    rows: Iterable[dict[str, object]],
    natural_key: list[str],
    source: str,
) -> DQScore:
    """Score integrity as fraction of rows whose natural key is unique."""
    if not natural_key:
        raise ValueError("natural_key must not be empty")
    rows_list = list(rows)
    sample = len(rows_list)
    if sample == 0:
        return DQScore(
            dimension="integrity", source=source, score=1.0, sample_size=0, failed_count=0
        )
    seen: dict[tuple[object, ...], int] = {}
    for row in rows_list:
        key = tuple(row.get(k) for k in natural_key)
        seen[key] = seen.get(key, 0) + 1
    failed = sum(count - 1 for count in seen.values() if count > 1)
    return DQScore(
        dimension="integrity",
        source=source,
        score=1.0 - failed / sample,
        sample_size=sample,
        failed_count=failed,
    )


def score_accuracy_value_in_range(
    rows: Iterable[dict[str, object]],
    field: str,
    min_value: float,
    max_value: float,
    source: str,
) -> DQScore:
    """Score accuracy as fraction of numeric values within ``[min_value, max_value]``."""
    if min_value > max_value:
        raise ValueError("min_value must be <= max_value")
    rows_list = list(rows)
    sample = len(rows_list)
    if sample == 0:
        return DQScore(
            dimension="accuracy", source=source, score=1.0, sample_size=0, failed_count=0
        )
    failed = 0
    for row in rows_list:
        value = row.get(field)
        if not isinstance(value, int | float) or isinstance(value, bool):
            failed += 1
            continue
        if value < min_value or value > max_value:
            failed += 1
    return DQScore(
        dimension="accuracy",
        source=source,
        score=1.0 - failed / sample,
        sample_size=sample,
        failed_count=failed,
    )


def utc_now() -> datetime:
    """Return a timezone-aware UTC ``datetime`` — used as ``snapshot_ts`` in Gold."""
    return datetime.now(tz=UTC)
