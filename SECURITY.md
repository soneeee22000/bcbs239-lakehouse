# Security

## Disclosure

This is a portfolio reference implementation operating on **synthetic data only**. There is no production deployment, no real customer data, no external network surface beyond outbound calls to a Databricks workspace.

If you find a security issue you believe is exploitable in a derived deployment, please email pyaesonekyaw101010@gmail.com rather than opening a public issue.

## What this repo does NOT handle

- Real Personally Identifiable Information (PII)
- Real Legal Entity Identifiers (every synthetic LEI is prefixed `9999`; an assertion in `src/bcbs239_lakehouse/data/synthetic.py::assert_synthetic` enforces this invariant; CI tests would fail if a real-looking LEI were ever introduced)
- Real customer counterparty data, exposures, or collateral
- Real Bank for International Settlements / regulator submissions

If you fork this repository to load real G-SIB data, the security model changes substantially — review **at minimum**:

1. Unity Catalog row-level access policies (currently the bundled provisioner does not bind RLS; see `docs/PORTABILITY.md` and `src/bcbs239_lakehouse/databricks/unity_catalog.py`)
2. Lakeview dashboard sharing scope (the bundled JSON spec does not set audience filters)
3. Source-system credentials handling (env vars only; never commit `.env`)
4. Bronze-layer raw CSV retention policy (currently never expires)
5. Audit-log capture for every cataloged read

## Dependencies

`uv sync` produces a fully-pinned lockfile (`uv.lock`). Dependency versions are reviewed manually before each release; `pip-audit` and `gitleaks` are recommended on top of CI.

## Secrets handling

- `.env` is gitignored. `.env.example` documents the required keys.
- Databricks tokens are never committed; the demo Makefile reads `DATABRICKS_HOST` / `DATABRICKS_TOKEN` from environment.
- Synthetic CSVs in `data/synthetic/` are gitignored.
- Local `warehouse/` Delta tables are gitignored.
