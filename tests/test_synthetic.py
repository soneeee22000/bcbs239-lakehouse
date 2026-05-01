"""Tests for the synthetic data generator."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from bcbs239_lakehouse.data.synthetic import (
    BASEL_RISK_WEIGHTS,
    COLLATERAL_TYPES,
    EXPOSURE_TYPES,
    IFRS9_STAGES,
    SYNTHETIC_COLLATERAL_PREFIX,
    SYNTHETIC_EXPOSURE_PREFIX,
    SYNTHETIC_LEI_PREFIX,
    Counterparty,
    assert_synthetic,
    generate_collateral,
    generate_counterparties,
    generate_exposures,
    main,
    write_synthetic_dataset,
)

# ── assert_synthetic ──────────────────────────────────────────────────


def test_assert_synthetic_accepts_synthetic_lei() -> None:
    assert_synthetic(f"{SYNTHETIC_LEI_PREFIX}0000000000000001")


def test_assert_synthetic_rejects_real_looking_lei() -> None:
    with pytest.raises(ValueError, match="synthetic prefix"):
        assert_synthetic("549300DTUYXVMJXZNY75")


# ── counterparty ──────────────────────────────────────────────────────


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
    rows = generate_counterparties(n=50, seed=42)
    for row in rows:
        assert_synthetic(row.lei)


def test_generate_counterparties_rejects_zero_n() -> None:
    with pytest.raises(ValueError, match="n must be >= 1"):
        generate_counterparties(n=0)


# ── exposure ──────────────────────────────────────────────────────────


def test_generate_exposures_deterministic() -> None:
    cps = generate_counterparties(n=10, seed=42)
    a = generate_exposures(cps, seed=42)
    b = generate_exposures(cps, seed=42)
    assert a == b


def test_generate_exposures_references_real_counterparties() -> None:
    cps = generate_counterparties(n=10, seed=42)
    valid_leis = {cp.lei for cp in cps}
    exposures = generate_exposures(cps, seed=42)
    assert all(exp.lei in valid_leis for exp in exposures)


def test_generate_exposures_synthetic_id_prefix() -> None:
    cps = generate_counterparties(n=5, seed=42)
    exposures = generate_exposures(cps, seed=42)
    assert all(exp.exposure_id.startswith(SYNTHETIC_EXPOSURE_PREFIX) for exp in exposures)


def test_generate_exposures_clean_invariants() -> None:
    """When cleanliness=1.0, every row satisfies the business invariants."""
    cps = generate_counterparties(n=10, seed=42)
    exposures = generate_exposures(cps, seed=42, cleanliness=1.0)
    for exp in exposures:
        assert exp.amount_eur > 0, f"{exp.exposure_id} has non-positive amount"
        assert exp.maturity_date > exp.as_of_date, f"{exp.exposure_id} matures before/on as_of_date"
        assert exp.risk_weight in BASEL_RISK_WEIGHTS, (
            f"{exp.exposure_id} has invalid risk weight {exp.risk_weight}"
        )
        assert exp.exposure_type in EXPOSURE_TYPES
        assert exp.ifrs9_stage in IFRS9_STAGES
        assert 1 <= exp.internal_rating <= 12


def test_generate_exposures_dirty_introduces_defects() -> None:
    """When cleanliness<1.0, at least one defect appears in a 50-counterparty sample."""
    cps = generate_counterparties(n=50, seed=42)
    exposures = generate_exposures(cps, seed=42, cleanliness=0.5)
    invariants_failed = sum(
        1
        for exp in exposures
        if exp.amount_eur <= 0
        or exp.maturity_date <= exp.as_of_date
        or exp.risk_weight not in BASEL_RISK_WEIGHTS
    )
    assert invariants_failed > 0, "cleanliness=0.5 should introduce visible defects"


def test_generate_exposures_rejects_empty_counterparties() -> None:
    with pytest.raises(ValueError, match="counterparties must not be empty"):
        generate_exposures([], seed=42)


def test_generate_exposures_rejects_invalid_cleanliness() -> None:
    cps = generate_counterparties(n=5, seed=42)
    with pytest.raises(ValueError, match=r"cleanliness must be in \[0, 1\]"):
        generate_exposures(cps, cleanliness=1.5)


# ── collateral ────────────────────────────────────────────────────────


def test_generate_collateral_deterministic() -> None:
    cps = generate_counterparties(n=10, seed=42)
    exposures = generate_exposures(cps, seed=42)
    a = generate_collateral(exposures, seed=42)
    b = generate_collateral(exposures, seed=42)
    assert a == b


def test_generate_collateral_synthetic_id_prefix() -> None:
    cps = generate_counterparties(n=5, seed=42)
    exposures = generate_exposures(cps, seed=42)
    collateral = generate_collateral(exposures, seed=42)
    assert all(c.collateral_id.startswith(SYNTHETIC_COLLATERAL_PREFIX) for c in collateral)


def test_generate_collateral_clean_references_real_exposures() -> None:
    """When cleanliness=1.0, every collateral row references a real exposure_id."""
    cps = generate_counterparties(n=10, seed=42)
    exposures = generate_exposures(cps, seed=42, cleanliness=1.0)
    valid_ids = {exp.exposure_id for exp in exposures}
    collateral = generate_collateral(exposures, seed=42, cleanliness=1.0)
    for c in collateral:
        assert c.exposure_id in valid_ids, f"{c.collateral_id} orphans {c.exposure_id}"


def test_generate_collateral_clean_invariants() -> None:
    cps = generate_counterparties(n=10, seed=42)
    exposures = generate_exposures(cps, seed=42, cleanliness=1.0)
    collateral = generate_collateral(exposures, seed=42, cleanliness=1.0)
    for c in collateral:
        assert c.value_eur >= 0
        assert 0.0 <= c.haircut_pct <= 1.0
        assert c.valuation_date <= exposures[0].as_of_date
        assert c.collateral_type in COLLATERAL_TYPES


def test_generate_collateral_dirty_introduces_defects() -> None:
    cps = generate_counterparties(n=50, seed=42)
    exposures = generate_exposures(cps, seed=42, cleanliness=1.0)
    valid_ids = {exp.exposure_id for exp in exposures}
    collateral = generate_collateral(exposures, seed=42, cleanliness=0.5)
    orphans = sum(1 for c in collateral if c.exposure_id not in valid_ids)
    future_valuations = sum(1 for c in collateral if c.valuation_date > exposures[0].as_of_date)
    assert (orphans + future_valuations) > 0, "cleanliness=0.5 should produce visible defects"


def test_generate_collateral_rejects_empty_exposures() -> None:
    with pytest.raises(ValueError, match="exposures must not be empty"):
        generate_collateral([], seed=42)


def test_generate_collateral_rejects_invalid_coverage() -> None:
    cps = generate_counterparties(n=5, seed=42)
    exposures = generate_exposures(cps, seed=42)
    with pytest.raises(ValueError, match=r"coverage_ratio must be in \[0, 1\]"):
        generate_collateral(exposures, coverage_ratio=1.5)


# ── write_synthetic_dataset + CLI ─────────────────────────────────────


def test_write_synthetic_dataset_produces_three_csvs(tmp_path: Path) -> None:
    counts = write_synthetic_dataset(tmp_path, n_counterparties=20, seed=42)
    assert (tmp_path / "counterparty.csv").exists()
    assert (tmp_path / "exposure.csv").exists()
    assert (tmp_path / "collateral.csv").exists()
    assert counts["counterparty"] == 20
    assert counts["exposure"] > 0
    assert counts["collateral"] > 0


def test_write_synthetic_dataset_csv_headers_are_correct(tmp_path: Path) -> None:
    write_synthetic_dataset(tmp_path, n_counterparties=5, seed=42)
    counterparty_lines = (tmp_path / "counterparty.csv").read_text(encoding="utf-8").splitlines()
    assert counterparty_lines[0] == "lei,legal_name,country_iso2,sector,parent_lei,inception_date"


def test_main_cli_clean(tmp_path: Path) -> None:
    exit_code = main(
        [
            "--output",
            str(tmp_path),
            "--seed",
            "42",
            "--counterparties",
            "10",
        ]
    )
    assert exit_code == 0
    assert (tmp_path / "counterparty.csv").exists()


def test_main_cli_inject_defects(tmp_path: Path) -> None:
    exit_code = main(
        [
            "--output",
            str(tmp_path),
            "--seed",
            "42",
            "--counterparties",
            "10",
            "--inject-defects",
        ]
    )
    assert exit_code == 0
    assert (tmp_path / "exposure.csv").exists()


# ── invariants we depend on across modules ────────────────────────────


def test_exposure_dataclass_is_frozen() -> None:
    cps = generate_counterparties(n=2, seed=42)
    exp = generate_exposures(cps, seed=42)[0]
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError
        exp.amount_eur = 0.0  # type: ignore[misc]


def test_collateral_dataclass_is_frozen() -> None:
    cps = generate_counterparties(n=2, seed=42)
    exposures = generate_exposures(cps, seed=42)
    col = generate_collateral(exposures, seed=42)
    if col:
        with pytest.raises((AttributeError, Exception)):
            col[0].value_eur = 0.0  # type: ignore[misc]


# ── reproducibility byte-equality across seeds ────────────────────────


def test_full_pipeline_byte_equal_for_same_seed(tmp_path: Path) -> None:
    """Same seed -> byte-equal CSV outputs across runs (CI determinism)."""
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    write_synthetic_dataset(out_a, n_counterparties=15, seed=42)
    write_synthetic_dataset(out_b, n_counterparties=15, seed=42)
    for name in ("counterparty.csv", "exposure.csv", "collateral.csv"):
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes(), (
            f"{name} differs between runs with same seed"
        )


def test_dates_used_in_test() -> None:
    """Sanity: as_of_date used in fixtures matches generator default."""
    cps = generate_counterparties(n=2, seed=42)
    exp = generate_exposures(cps, seed=42)[0]
    assert exp.as_of_date == date(2026, 3, 31)
