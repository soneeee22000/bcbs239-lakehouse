"""Tests for the synthetic data generator."""

from __future__ import annotations

import pytest

from bcbs239_lakehouse.data.synthetic import (
    SYNTHETIC_LEI_PREFIX,
    Counterparty,
    assert_synthetic,
    generate_counterparties,
)


def test_assert_synthetic_accepts_synthetic_lei() -> None:
    assert_synthetic(f"{SYNTHETIC_LEI_PREFIX}0000000000000001")


def test_assert_synthetic_rejects_real_looking_lei() -> None:
    with pytest.raises(ValueError, match="synthetic prefix"):
        assert_synthetic("549300DTUYXVMJXZNY75")  # looks like a real LEI


def test_generate_counterparties_returns_requested_count() -> None:
    rows = generate_counterparties(n=10, seed=42)
    assert len(rows) == 10
    assert all(isinstance(row, Counterparty) for row in rows)


def test_generate_counterparties_is_deterministic_for_same_seed() -> None:
    a = generate_counterparties(n=20, seed=42)
    b = generate_counterparties(n=20, seed=42)
    assert a == b


def test_generate_counterparties_differs_for_different_seed() -> None:
    a = generate_counterparties(n=20, seed=42)
    b = generate_counterparties(n=20, seed=43)
    assert a != b


def test_generate_counterparties_all_synthetic_leis() -> None:
    """Every generated LEI must start with the synthetic prefix — non-negotiable."""
    rows = generate_counterparties(n=50, seed=42)
    for row in rows:
        assert_synthetic(row.lei)


def test_generate_counterparties_rejects_zero_n() -> None:
    with pytest.raises(ValueError, match="n must be >= 1"):
        generate_counterparties(n=0)
