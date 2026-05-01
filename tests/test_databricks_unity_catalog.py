"""Tests for the Unity Catalog provisioner (mocked databricks-sdk)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bcbs239_lakehouse.databricks.unity_catalog import (
    DEFAULT_LAYER_SCHEMAS,
    UnityCatalogProvisioner,
)


class _AlreadyExistsError(Exception):
    """Mirrors what databricks-sdk raises when a resource already exists."""


def _client_with_apis() -> MagicMock:
    """Build a WorkspaceClient mock with .catalogs / .schemas / .tables / .lakeview."""
    client = MagicMock()
    client.catalogs = MagicMock()
    client.schemas = MagicMock()
    client.tables = MagicMock()
    client.lakeview = MagicMock()
    return client


# ── catalog ───────────────────────────────────────────────────────────


def test_provision_catalog_creates_when_absent() -> None:
    client = _client_with_apis()
    p = UnityCatalogProvisioner(client, catalog_name="bcbs239_lakehouse")
    result = p.provision_catalog()
    assert result.created is True
    assert result.full_name == "bcbs239_lakehouse"
    client.catalogs.create.assert_called_once_with(name="bcbs239_lakehouse")


def test_provision_catalog_idempotent_on_already_exists() -> None:
    client = _client_with_apis()
    client.catalogs.create.side_effect = _AlreadyExistsError(
        "Catalog 'bcbs239_lakehouse' already exists"
    )
    p = UnityCatalogProvisioner(client, catalog_name="bcbs239_lakehouse")
    result = p.provision_catalog()
    assert result.created is False
    assert result.full_name == "bcbs239_lakehouse"


def test_provision_catalog_propagates_other_errors() -> None:
    client = _client_with_apis()
    client.catalogs.create.side_effect = RuntimeError("network unreachable")
    p = UnityCatalogProvisioner(client, catalog_name="bcbs239_lakehouse")
    with pytest.raises(RuntimeError, match="network unreachable"):
        p.provision_catalog()


# ── schema ────────────────────────────────────────────────────────────


def test_provision_schema_creates_when_absent() -> None:
    client = _client_with_apis()
    p = UnityCatalogProvisioner(client, catalog_name="bcbs239_lakehouse")
    result = p.provision_schema("bronze")
    assert result.created is True
    assert result.full_name == "bcbs239_lakehouse.bronze"
    client.schemas.create.assert_called_once_with(name="bronze", catalog_name="bcbs239_lakehouse")


def test_provision_schema_idempotent_on_already_exists() -> None:
    client = _client_with_apis()
    client.schemas.create.side_effect = _AlreadyExistsError("schema already_exists")
    p = UnityCatalogProvisioner(client, catalog_name="bcbs239_lakehouse")
    result = p.provision_schema("silver")
    assert result.created is False
    assert result.full_name == "bcbs239_lakehouse.silver"


def test_provision_layer_schemas_creates_three() -> None:
    client = _client_with_apis()
    p = UnityCatalogProvisioner(client, catalog_name="bcbs239_lakehouse")
    results = p.provision_layer_schemas()
    assert [r.full_name.rsplit(".", 1)[-1] for r in results] == list(DEFAULT_LAYER_SCHEMAS)
    assert client.schemas.create.call_count == 3


# ── external Delta table ──────────────────────────────────────────────


def test_register_external_delta_table_creates_when_absent() -> None:
    client = _client_with_apis()
    p = UnityCatalogProvisioner(client, catalog_name="bcbs239_lakehouse")
    result = p.register_external_delta_table(
        schema_name="bronze",
        table_name="counterparty",
        storage_location="s3://my-bucket/bcbs239/bronze/counterparty",
    )
    assert result.created is True
    assert result.full_name == "bcbs239_lakehouse.bronze.counterparty"
    kwargs = client.tables.create.call_args.kwargs
    assert kwargs["name"] == "counterparty"
    assert kwargs["catalog_name"] == "bcbs239_lakehouse"
    assert kwargs["schema_name"] == "bronze"
    assert kwargs["table_type"] == "EXTERNAL"
    assert kwargs["data_source_format"] == "DELTA"
    assert kwargs["storage_location"].endswith("/counterparty")


def test_register_external_delta_table_idempotent() -> None:
    client = _client_with_apis()
    client.tables.create.side_effect = _AlreadyExistsError("Table 'counterparty' AlreadyExists")
    p = UnityCatalogProvisioner(client, catalog_name="bcbs239_lakehouse")
    result = p.register_external_delta_table(
        schema_name="bronze",
        table_name="counterparty",
        storage_location="s3://my-bucket/bcbs239/bronze/counterparty",
    )
    assert result.created is False


# ── full provision flow ──────────────────────────────────────────────


def test_provision_full_lakehouse_no_external_tables() -> None:
    client = _client_with_apis()
    p = UnityCatalogProvisioner(client, catalog_name="bcbs239_lakehouse")
    results = p.provision_full_lakehouse()
    # 1 catalog + 3 schemas
    assert len(results) == 4
    assert "catalog" in results
    assert "schema:bcbs239_lakehouse.bronze" in results
    assert "schema:bcbs239_lakehouse.silver" in results
    assert "schema:bcbs239_lakehouse.gold" in results
    assert client.catalogs.create.call_count == 1
    assert client.schemas.create.call_count == 3
    assert client.tables.create.call_count == 0


def test_provision_full_lakehouse_with_external_tables() -> None:
    client = _client_with_apis()
    p = UnityCatalogProvisioner(client, catalog_name="bcbs239_lakehouse")
    results = p.provision_full_lakehouse(
        external_locations={
            "bronze": {
                "counterparty": "s3://b/bronze/counterparty",
                "exposure": "s3://b/bronze/exposure",
            },
            "gold": {"fact_dq_scorecard": "s3://b/gold/fact_dq_scorecard"},
        }
    )
    assert "table:bcbs239_lakehouse.bronze.counterparty" in results
    assert "table:bcbs239_lakehouse.bronze.exposure" in results
    assert "table:bcbs239_lakehouse.gold.fact_dq_scorecard" in results
    assert client.tables.create.call_count == 3
