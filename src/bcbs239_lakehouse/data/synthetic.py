"""Synthetic risk data generator for bcbs239-lakehouse.

Deterministic given a seed; obvious-fake identifiers (LEI prefix 9999, names like
"AcmeBank S.A."). Real G-SIB data is OUT OF SCOPE forever per PRD section 8.

Weekend 1 ships counterparty + exposure + collateral generators; defect injection
extends with controllable cleanliness profiles for PRD Story 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from random import Random

SYNTHETIC_LEI_PREFIX = "9999"
SYNTHETIC_NAME_SUFFIXES = ("S.A.", "PLC", "GmbH", "N.V.", "AG")
SYNTHETIC_COUNTRIES = ("FR", "DE", "NL", "GB", "IT", "ES", "BE", "LU")
SYNTHETIC_SECTORS = (
    "BANKS",
    "INSURANCE",
    "ASSET_MANAGEMENT",
    "CORPORATE_NON_FIN",
    "SOVEREIGN",
)


@dataclass(frozen=True)
class Counterparty:
    """Synthetic legal-entity master row.

    LEI is always prefixed with 9999 to mark the row as obviously fake; tests
    enforce this invariant via :func:`bcbs239_lakehouse.data.synthetic.assert_synthetic`.
    """

    lei: str
    legal_name: str
    country_iso2: str
    sector: str
    parent_lei: str | None
    inception_date: date


def assert_synthetic(lei: str) -> None:
    """Raise ``ValueError`` if ``lei`` does not look like a synthetic identifier.

    BCBS 239 work touches highly sensitive data; we keep an explicit guard so
    that any accidental real-LEI reintroduction surfaces loudly in tests.
    """
    if not lei.startswith(SYNTHETIC_LEI_PREFIX):
        raise ValueError(
            f"LEI {lei!r} does not start with synthetic prefix {SYNTHETIC_LEI_PREFIX!r} — "
            "real-data is out of scope for this repo per PRD section 8."
        )


def generate_counterparties(n: int, seed: int = 42) -> list[Counterparty]:
    """Generate ``n`` synthetic counterparties deterministically.

    Same ``(n, seed)`` tuple yields byte-equal output across runs — required
    for reproducibility in CI and for the PRD Story 3 defect-injection cycle.
    """
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
