"""Synthetic risk data generator for bcbs239-lakehouse.

Deterministic given a seed; obvious-fake identifiers (LEI prefix 9999, names like
"AcmeBank S.A."). Real G-SIB data is OUT OF SCOPE forever per PRD section 8.

W1-S1 ships counterparty + exposure + collateral generators with controllable
``cleanliness`` parameter (0.0 = maximally dirty, 1.0 = clean). PRD Story 3
defect-injection scripts in W2 wrap the dirty mode with a CLI handle.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from random import Random

SYNTHETIC_LEI_PREFIX = "9999"
SYNTHETIC_EXPOSURE_PREFIX = "EXP9999"
SYNTHETIC_COLLATERAL_PREFIX = "COL9999"
SYNTHETIC_NAME_SUFFIXES = ("S.A.", "PLC", "GmbH", "N.V.", "AG")
SYNTHETIC_COUNTRIES = ("FR", "DE", "NL", "GB", "IT", "ES", "BE", "LU")
SYNTHETIC_SECTORS = (
    "BANKS",
    "INSURANCE",
    "ASSET_MANAGEMENT",
    "CORPORATE_NON_FIN",
    "SOVEREIGN",
)

EXPOSURE_TYPES = ("LOAN", "DEBT_SECURITY", "DERIVATIVE", "OFF_BALANCE_SHEET")
BASEL_RISK_WEIGHTS = (0.0, 0.2, 0.5, 0.75, 1.0, 1.5)
IFRS9_STAGES = ("STAGE_1", "STAGE_2", "STAGE_3")
COLLATERAL_TYPES = ("CASH", "GOVERNMENT_BOND", "EQUITY", "REAL_ESTATE")


@dataclass(frozen=True)
class Counterparty:
    """Synthetic legal-entity master row.

    LEI is always prefixed with 9999 to mark the row as obviously fake.
    """

    lei: str
    legal_name: str
    country_iso2: str
    sector: str
    parent_lei: str | None
    inception_date: date


@dataclass(frozen=True)
class Exposure:
    """Synthetic credit exposure to a counterparty.

    ``exposure_id`` always carries the synthetic prefix. Amount is in EUR (whole units).
    Maturity is always strictly after ``as_of_date`` for a clean row; cleanliness
    parameter controls whether this invariant may be violated.
    """

    exposure_id: str
    lei: str
    exposure_type: str
    amount_eur: float
    as_of_date: date
    maturity_date: date
    risk_weight: float
    ifrs9_stage: str
    internal_rating: int


@dataclass(frozen=True)
class Collateral:
    """Synthetic collateral pledge against an exposure.

    ``collateral_id`` always carries the synthetic prefix. ``haircut_pct`` is a
    fraction in [0, 1]; ``value_eur`` is post-haircut market value.
    """

    collateral_id: str
    exposure_id: str
    collateral_type: str
    value_eur: float
    haircut_pct: float
    valuation_date: date
    pledge_date: date


def assert_synthetic(lei: str) -> None:
    """Raise ``ValueError`` if ``lei`` does not look like a synthetic identifier."""
    if not lei.startswith(SYNTHETIC_LEI_PREFIX):
        raise ValueError(
            f"LEI {lei!r} does not start with synthetic prefix {SYNTHETIC_LEI_PREFIX!r} — "
            "real-data is out of scope for this repo per PRD section 8."
        )


def _validate_cleanliness(cleanliness: float) -> None:
    if not 0.0 <= cleanliness <= 1.0:
        raise ValueError(f"cleanliness must be in [0, 1], got {cleanliness}")


def generate_counterparties(n: int, seed: int = 42) -> list[Counterparty]:
    """Generate ``n`` synthetic counterparties deterministically."""
    if n < 1:
        raise ValueError("n must be >= 1")
    rng = Random(seed)  # noqa: S311 — synthetic test data, crypto-grade RNG not required
    base_date = date(2010, 1, 1)
    out: list[Counterparty] = []
    for i in range(n):
        lei = f"{SYNTHETIC_LEI_PREFIX}{i:016d}"
        suffix = rng.choice(SYNTHETIC_NAME_SUFFIXES)
        legal_name = f"AcmeEntity{i:04d} {suffix}"
        country = rng.choice(SYNTHETIC_COUNTRIES)
        sector = rng.choice(SYNTHETIC_SECTORS)
        parent = out[rng.randrange(len(out))].lei if out and rng.random() < 0.3 else None
        inception = base_date + timedelta(days=rng.randint(0, 365 * 14))
        out.append(
            Counterparty(
                lei=lei,
                legal_name=legal_name,
                country_iso2=country,
                sector=sector,
                parent_lei=parent,
                inception_date=inception,
            )
        )
    return out


def generate_exposures(
    counterparties: Sequence[Counterparty],
    n_per_counterparty_avg: int = 3,
    as_of_date: date = date(2026, 3, 31),
    seed: int = 42,
    cleanliness: float = 1.0,
) -> list[Exposure]:
    """Generate exposures against the supplied counterparties.

    Roughly ``n_per_counterparty_avg`` exposures per counterparty (Poisson-ish via
    rng.randint(1, 2*avg-1)). When ``cleanliness < 1.0``, a fraction of rows
    receive deliberate defects (negative amount, maturity before as_of_date,
    invalid risk weight) — these surface as DQ scorecard drops.
    """
    if not counterparties:
        raise ValueError("counterparties must not be empty")
    if n_per_counterparty_avg < 1:
        raise ValueError("n_per_counterparty_avg must be >= 1")
    _validate_cleanliness(cleanliness)
    rng = Random(seed)  # noqa: S311
    out: list[Exposure] = []
    counter = 0
    for cp in counterparties:
        n = rng.randint(1, max(1, 2 * n_per_counterparty_avg - 1))
        for _ in range(n):
            exposure_id = f"{SYNTHETIC_EXPOSURE_PREFIX}{counter:012d}"
            counter += 1
            exposure_type = rng.choice(EXPOSURE_TYPES)
            amount = round(rng.uniform(10_000.0, 50_000_000.0), 2)
            tenor_days = rng.randint(30, 365 * 10)
            maturity = as_of_date + timedelta(days=tenor_days)
            risk_weight = rng.choice(BASEL_RISK_WEIGHTS)
            stage = rng.choices(IFRS9_STAGES, weights=[0.85, 0.12, 0.03], k=1)[0]
            rating = rng.randint(1, 12)

            # Defect injection — only when cleanliness < 1.0
            if cleanliness < 1.0 and rng.random() > cleanliness:
                defect = rng.choice(("negative_amount", "early_maturity", "bad_risk_weight"))
                if defect == "negative_amount":
                    amount = -amount
                elif defect == "early_maturity":
                    maturity = as_of_date - timedelta(days=rng.randint(1, 30))
                else:
                    risk_weight = -1.0  # not in BASEL_RISK_WEIGHTS

            out.append(
                Exposure(
                    exposure_id=exposure_id,
                    lei=cp.lei,
                    exposure_type=exposure_type,
                    amount_eur=amount,
                    as_of_date=as_of_date,
                    maturity_date=maturity,
                    risk_weight=risk_weight,
                    ifrs9_stage=stage,
                    internal_rating=rating,
                )
            )
    return out


def generate_collateral(
    exposures: Sequence[Exposure],
    coverage_ratio: float = 0.6,
    seed: int = 42,
    cleanliness: float = 1.0,
) -> list[Collateral]:
    """Generate collateral pledges for a fraction of the supplied exposures.

    ``coverage_ratio`` in [0, 1] is the probability each exposure has at least one
    collateral row. When ``cleanliness < 1.0``, deliberate defects surface
    (orphan ``exposure_id``, value > exposure amount, valuation_date in future).
    """
    if not exposures:
        raise ValueError("exposures must not be empty")
    if not 0.0 <= coverage_ratio <= 1.0:
        raise ValueError(f"coverage_ratio must be in [0, 1], got {coverage_ratio}")
    _validate_cleanliness(cleanliness)
    rng = Random(seed)  # noqa: S311
    out: list[Collateral] = []
    counter = 0
    for exp in exposures:
        if rng.random() > coverage_ratio:
            continue
        n_pledges = rng.randint(1, 3)
        for _ in range(n_pledges):
            collateral_id = f"{SYNTHETIC_COLLATERAL_PREFIX}{counter:012d}"
            counter += 1
            ctype = rng.choice(COLLATERAL_TYPES)
            haircut = round(rng.uniform(0.0, 0.4), 4)
            base_value = abs(exp.amount_eur) * rng.uniform(0.2, 1.5)
            value = round(base_value * (1.0 - haircut), 2)
            valuation = exp.as_of_date - timedelta(days=rng.randint(0, 90))
            pledge = exp.as_of_date - timedelta(days=rng.randint(90, 365 * 5))

            exposure_id_ref = exp.exposure_id
            if cleanliness < 1.0 and rng.random() > cleanliness:
                defect = rng.choice(("orphan", "over_value", "future_valuation"))
                if defect == "orphan":
                    exposure_id_ref = f"{SYNTHETIC_EXPOSURE_PREFIX}{'9' * 12}"
                elif defect == "over_value":
                    value = abs(exp.amount_eur) * 5.0
                else:
                    valuation = exp.as_of_date + timedelta(days=rng.randint(30, 180))

            out.append(
                Collateral(
                    collateral_id=collateral_id,
                    exposure_id=exposure_id_ref,
                    collateral_type=ctype,
                    value_eur=value,
                    haircut_pct=haircut,
                    valuation_date=valuation,
                    pledge_date=pledge,
                )
            )
    return out


def _write_csv(rows: Sequence[object], path: Path, fieldnames: list[str]) -> int:
    """Write a sequence of frozen dataclasses to CSV. Returns row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: v for k, v in asdict(row).items() if k in fieldnames})  # type: ignore[call-overload]
    return len(rows)


def write_synthetic_dataset(
    output_dir: Path,
    n_counterparties: int = 100,
    seed: int = 42,
    cleanliness: float = 1.0,
) -> dict[str, int]:
    """Generate the full synthetic dataset and write CSVs to ``output_dir``.

    Returns a dict mapping table name to row count.
    """
    counterparties = generate_counterparties(n_counterparties, seed=seed)
    exposures = generate_exposures(counterparties, seed=seed, cleanliness=cleanliness)
    collateral = generate_collateral(exposures, seed=seed, cleanliness=cleanliness)

    counts = {
        "counterparty": _write_csv(
            counterparties,
            output_dir / "counterparty.csv",
            ["lei", "legal_name", "country_iso2", "sector", "parent_lei", "inception_date"],
        ),
        "exposure": _write_csv(
            exposures,
            output_dir / "exposure.csv",
            [
                "exposure_id",
                "lei",
                "exposure_type",
                "amount_eur",
                "as_of_date",
                "maturity_date",
                "risk_weight",
                "ifrs9_stage",
                "internal_rating",
            ],
        ),
        "collateral": _write_csv(
            collateral,
            output_dir / "collateral.csv",
            [
                "collateral_id",
                "exposure_id",
                "collateral_type",
                "value_eur",
                "haircut_pct",
                "valuation_date",
                "pledge_date",
            ],
        ),
    }
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m bcbs239_lakehouse.data.synthetic --output ...``."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic counterparty + exposure + collateral CSVs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory to write counterparty.csv, exposure.csv, collateral.csv into.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--counterparties",
        type=int,
        default=100,
        help="Number of synthetic counterparties (default: 100).",
    )
    parser.add_argument(
        "--inject-defects",
        action="store_true",
        help="Generate the 'dirty' variant (cleanliness=0.7) for PRD Story 3.",
    )
    args = parser.parse_args(argv)
    cleanliness = 0.7 if args.inject_defects else 1.0
    counts = write_synthetic_dataset(
        args.output,
        n_counterparties=args.counterparties,
        seed=args.seed,
        cleanliness=cleanliness,
    )
    sys.stdout.write(
        f"Wrote synthetic dataset to {args.output} (cleanliness={cleanliness}): "
        f"counterparty={counts['counterparty']}, "
        f"exposure={counts['exposure']}, "
        f"collateral={counts['collateral']}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
