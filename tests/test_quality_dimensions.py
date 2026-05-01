"""Tests for the 4 BCBS 239 data-quality dimension scorers."""

from __future__ import annotations

from datetime import date

import pytest

from bcbs239_lakehouse.quality.dimensions import (
    DQScore,
    score_accuracy_value_in_range,
    score_completeness,
    score_integrity_dedup,
    score_timeliness,
)

# ── DQScore invariants ────────────────────────────────────────────────


def test_dqscore_rejects_invalid_dimension() -> None:
    with pytest.raises(ValueError, match="dimension must be one of"):
        DQScore(dimension="freshness", source="x", score=1.0, sample_size=0, failed_count=0)


def test_dqscore_rejects_score_above_one() -> None:
    with pytest.raises(ValueError, match=r"score must be in \[0, 1\]"):
        DQScore(dimension="completeness", source="x", score=1.1, sample_size=0, failed_count=0)


def test_dqscore_rejects_failed_exceeds_sample() -> None:
    with pytest.raises(ValueError, match="failed_count cannot exceed"):
        DQScore(dimension="completeness", source="x", score=0.0, sample_size=5, failed_count=10)


# ── completeness ──────────────────────────────────────────────────────


def test_completeness_perfect_when_no_nulls() -> None:
    rows = [
        {"lei": "9999A", "legal_name": "AcmeBank S.A.", "country_iso2": "FR"},
        {"lei": "9999B", "legal_name": "Other AG", "country_iso2": "DE"},
    ]
    score = score_completeness(rows, required_fields=["lei", "legal_name"], source="counterparty")
    assert score.score == 1.0
    assert score.failed_count == 0


def test_completeness_drops_with_missing_field() -> None:
    rows = [
        {"lei": "9999A", "legal_name": "AcmeBank S.A."},
        {"lei": "9999B", "legal_name": None},
        {"lei": None, "legal_name": "Third"},
    ]
    score = score_completeness(rows, required_fields=["lei", "legal_name"], source="counterparty")
    assert score.failed_count == 2
    assert score.score == pytest.approx(1.0 - 2 / 3)


def test_completeness_empty_input_scores_one() -> None:
    """No rows = nothing to fail."""
    score = score_completeness([], required_fields=["lei"], source="counterparty")
    assert score.score == 1.0
    assert score.sample_size == 0


def test_completeness_rejects_empty_required_fields() -> None:
    with pytest.raises(ValueError, match="required_fields must not be empty"):
        score_completeness([{"a": 1}], required_fields=[], source="x")


# ── timeliness ────────────────────────────────────────────────────────


def test_timeliness_all_within_window() -> None:
    snaps = [date(2026, 5, 1), date(2026, 4, 30), date(2026, 5, 2)]
    score = score_timeliness(
        snaps, expected_snapshot=date(2026, 5, 1), max_lag_days=1, source="exposure"
    )
    assert score.score == 1.0


def test_timeliness_drops_with_late_snapshot() -> None:
    snaps = [date(2026, 5, 1), date(2026, 4, 1)]
    score = score_timeliness(
        snaps, expected_snapshot=date(2026, 5, 1), max_lag_days=2, source="exposure"
    )
    assert score.failed_count == 1
    assert score.score == 0.5


def test_timeliness_rejects_negative_lag() -> None:
    with pytest.raises(ValueError, match="max_lag_days must be non-negative"):
        score_timeliness([], expected_snapshot=date(2026, 5, 1), max_lag_days=-1, source="x")


# ── integrity (deduplication) ─────────────────────────────────────────


def test_integrity_no_duplicates() -> None:
    rows = [{"lei": "9999A"}, {"lei": "9999B"}, {"lei": "9999C"}]
    score = score_integrity_dedup(rows, natural_key=["lei"], source="counterparty")
    assert score.score == 1.0


def test_integrity_with_one_duplicate() -> None:
    rows = [{"lei": "9999A"}, {"lei": "9999A"}, {"lei": "9999B"}]
    score = score_integrity_dedup(rows, natural_key=["lei"], source="counterparty")
    assert score.failed_count == 1
    assert score.score == pytest.approx(2 / 3)


def test_integrity_compound_natural_key() -> None:
    rows = [
        {"lei": "9999A", "as_of": "2026-01-01"},
        {"lei": "9999A", "as_of": "2026-02-01"},
        {"lei": "9999A", "as_of": "2026-01-01"},  # dup
    ]
    score = score_integrity_dedup(rows, natural_key=["lei", "as_of"], source="exposure")
    assert score.failed_count == 1


# ── accuracy (value-in-range) ─────────────────────────────────────────


def test_accuracy_all_in_range() -> None:
    rows = [{"rwa": 100.0}, {"rwa": 200.0}, {"rwa": 50.0}]
    score = score_accuracy_value_in_range(
        rows, field="rwa", min_value=0.0, max_value=1000.0, source="exposure"
    )
    assert score.score == 1.0


def test_accuracy_drops_for_out_of_range() -> None:
    rows = [{"rwa": 100.0}, {"rwa": -10.0}, {"rwa": 50.0}, {"rwa": 5000.0}]
    score = score_accuracy_value_in_range(
        rows, field="rwa", min_value=0.0, max_value=1000.0, source="exposure"
    )
    assert score.failed_count == 2
    assert score.score == 0.5


def test_accuracy_drops_for_non_numeric() -> None:
    rows = [{"rwa": "n/a"}, {"rwa": None}, {"rwa": 100.0}]
    score = score_accuracy_value_in_range(
        rows, field="rwa", min_value=0.0, max_value=1000.0, source="exposure"
    )
    assert score.failed_count == 2


def test_accuracy_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="min_value must be <= max_value"):
        score_accuracy_value_in_range([], field="x", min_value=10.0, max_value=0.0, source="y")
