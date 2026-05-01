.PHONY: setup synthetic pipeline demo inject-defects repair-data lint test smoke ci uc-provision uc-teardown lakeview-provision clean

PYTHON ?= python

# ── Setup ─────────────────────────────────────────────────────────────
setup:
	uv sync --extra dev --extra dbt

# ── Development ───────────────────────────────────────────────────────
synthetic:
	$(PYTHON) -m bcbs239_lakehouse.data.synthetic --output data/synthetic --seed 42

pipeline:
	uv run python -m bcbs239_lakehouse.cli --root warehouse --synthetic-dir data/synthetic

demo:
	uv run python -m bcbs239_lakehouse.cli --root warehouse --synthetic-dir data/synthetic --counterparties 100 --seed 42

inject-defects:
	uv run python -m bcbs239_lakehouse.cli --root warehouse --synthetic-dir data/synthetic --counterparties 100 --seed 42 --inject-defects

repair-data:
	uv run python -m bcbs239_lakehouse.cli --root warehouse --synthetic-dir data/synthetic --counterparties 100 --seed 42

# ── Quality gates ─────────────────────────────────────────────────────
lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run mypy src

test:
	uv run pytest

smoke:
	uv run pytest -m smoke -v

ci: lint test
	@echo "[bcbs239-lakehouse] CI suite passed."

# ── Databricks provisioning (idempotent) ──────────────────────────────
uc-provision:
	@echo "[bcbs239-lakehouse] Unity Catalog provisioning lands in Weekend 2."

uc-teardown:
	@echo "[bcbs239-lakehouse] Unity Catalog teardown lands in Weekend 2."

lakeview-provision:
	@echo "[bcbs239-lakehouse] Lakeview dashboard provisioning lands in Weekend 2."

# ── Housekeeping ──────────────────────────────────────────────────────
clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml
	rm -rf spark-warehouse metastore_db derby.log
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
