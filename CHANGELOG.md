# Changelog

All notable changes to bcbs239-lakehouse. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned for v1.1

- Great Expectations 1.x migration — wrap each existing `bcbs239_lakehouse.quality.dimensions` scorer in a corresponding GE Expectation, run via a checkpoint inside the Databricks notebook path. The pure-Python scorers stay as the local-first reference.
- Live Databricks Community Edition demo run with screenshots of the published Lakeview dashboard
- 30-second walkthrough GIF capturing scorecard reaction to `make inject-defects`
- BCBS 239 principle 4-of-14 expansion — adaptability and frequency dimensions

## [0.2.0] — 2026-05-01

Weekend 2: Databricks-runtime adapters + portability docs + ship-ready polish.

### Added

- **Unity Catalog provisioner** (`src/bcbs239_lakehouse/databricks/unity_catalog.py`) — `UnityCatalogProvisioner` wrapping `databricks-sdk`. Idempotent catalog + schema + external Delta table provisioning; full `provision_full_lakehouse` end-to-end flow.
- **Lakeview dashboard publisher** (`src/bcbs239_lakehouse/databricks/lakeview.py`) — `LakeviewPublisher` reading the bundled JSON spec and creating-or-updating the dashboard via the SDK.
- **Lakeview JSON spec** (`src/bcbs239_lakehouse/databricks/dashboards/dq_scorecard.json`) — 5-widget BCBS 239 DQ scorecard: 4 score counters (completeness / accuracy / timeliness / integrity) + a multi-line trend chart bound to `bcbs239_lakehouse.gold.fact_dq_scorecard`.
- **15 mocked-SDK tests** (`tests/test_databricks_unity_catalog.py`, `tests/test_databricks_lakeview.py`) — assert idempotency, error-passthrough, JSON-spec validity, create-vs-update branching.
- **`docs/PORTABILITY.md`** — layer-by-layer Databricks ↔ Snowflake equivalence matrix with code-path swaps for Bronze ingestion (Auto Loader → Snowpipe), catalog (UC → Horizon), dashboards (Lakeview → Streamlit-in-Snowflake), and dbt profile.
- **README polish** — Mermaid diagram, demo CLI output snippet (clean + dirty runs side by side), explicit "what's covered, what isn't" BCBS 239 principle scope, dual-runtime architecture diagram.

### Changed

- Coverage gate raised to 80% (was 70% Weekend 1 floor); current TOTAL coverage 94.74% across 109 tests.
- README architecture section split into "library path" (Polars + delta-rs, locally testable) vs "Databricks runtime path" (notebooks + UC + Lakeview, requires a workspace).

### Test count

109 tests, 94.74% coverage (was 94 tests / 94.82% at end of Weekend 1).

## [0.1.0] — 2026-05-01

Weekend 1: scaffolding + Bronze + Silver + Gold + end-to-end demo CLI.

### Added

- **Project scaffolding** with PRD-driven scope (`docs/PRD.md`), 10-rule project CLAUDE.md, 4 of 14 BCBS 239 principles in scope, killed-claim discipline locked in PRD Appendix B.
- **Synthetic data generators** (`src/bcbs239_lakehouse/data/synthetic.py`) — `Counterparty`, `Exposure`, `Collateral` frozen dataclasses; deterministic seed; controllable `cleanliness` parameter for PRD Story 3 defect injection (negative amount, early maturity, bad risk weight, orphan exposure id, future valuation date). CLI: `python -m bcbs239_lakehouse.data.synthetic --output ... --seed 42 [--inject-defects]`.
- **DQ dimension scorers** (`src/bcbs239_lakehouse/quality/dimensions.py`) — pure-function scorers for the 4 data-engineerable BCBS 239 principles (completeness, accuracy, timeliness, integrity).
- **Bronze ingestion** (`src/bcbs239_lakehouse/pipeline/bronze.py`) — Polars + delta-rs idempotent CSV → Delta auto-loader pattern with `_ingest_log` checkpoint table.
- **Silver layer** (`src/bcbs239_lakehouse/pipeline/silver.py`) — typed casts, dedup keeping latest by `silver_loaded_at`, business-rule violations preserved for downstream DQ scoring.
- **Gold layer** (`src/bcbs239_lakehouse/pipeline/gold.py`) — `fact_rwa_aggregation` and `fact_dq_scorecard` marts.
- **End-to-end orchestrator CLI** (`src/bcbs239_lakehouse/cli.py`) — synthetic → bronze → silver → gold + scorecard summary print.
- **94 tests at 94.82% coverage** — pure-Polars + delta-rs path is fully runnable on Windows / macOS / Linux without Java.
- **CI** (`.github/workflows/ci.yml`) — ruff + mypy strict + pytest.
- **ADR-001** (`docs/ADR/ADR-001-delta-rs-for-library-path.md`) — split library path (Polars + deltalake-rs, no JVM) from notebooks path (PySpark + delta-spark, Databricks-runtime).

### Decided

- Killed-claim discipline (no Collibra / Alation / Atlan / Capgemini / Big-4 displacement framing) — anti-regression test in `tests/test_repo_hygiene.py`.
- Approved framing: "reference implementation of the BCBS 239 risk-data-aggregation lakehouse pattern Capgemini Risk Data Insights and Big-4 BCBS 239 advisory practices recommend G-SIBs build atop Databricks Unity Catalog".
- Scope cuts (per PRD §8): synthetic data only; 4 of 14 principles; no external Airflow (csrd-lake's territory); Databricks Community Edition (no paid workspace).

[Unreleased]: https://github.com/soneeee22000/bcbs239-lakehouse/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/soneeee22000/bcbs239-lakehouse/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/soneeee22000/bcbs239-lakehouse/releases/tag/v0.1.0
