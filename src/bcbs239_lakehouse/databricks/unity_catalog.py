"""Unity Catalog provisioning — idempotent catalog / schema / external-table setup.

Targets a Databricks Community Edition workspace (free tier). Each entry point
is idempotent: re-running a provision call when the resource already exists is
a successful no-op, never an error. This is the contract the demo Makefile
relies on so that ``make uc-provision`` can be run repeatedly during interview
walk-throughs without state-management bookkeeping.

The module deliberately wraps ``databricks-sdk`` rather than reaching for
``databricks-cli`` so the same code path can run from a notebook, a Python
script, or a CI job with identical semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:  # pragma: no cover — import only for type checking
    from databricks.sdk import WorkspaceClient


# Layer schemas to provision under the project catalog.
DEFAULT_LAYER_SCHEMAS = ("bronze", "silver", "gold")


@dataclass(frozen=True)
class ProvisionResult:
    """Outcome of an idempotent provision call."""

    full_name: str
    created: bool  # True = first provision; False = already existed (no-op)


def _is_already_exists(exc: BaseException) -> bool:
    """Return True if ``exc`` is the SDK's resource-already-exists error.

    The SDK raises a specific subclass but the tests want to mock without
    pulling the exception class — duck-typing on the str repr is enough
    here because the message is stable across SDK versions.
    """
    msg = str(exc).lower()
    return any(token in msg for token in ("already exists", "already_exists", "alreadyexists"))


class UnityCatalogProvisioner:
    """Idempotent provisioner for the project's UC catalog + schemas + tables."""

    def __init__(self, client: WorkspaceClient, catalog_name: str) -> None:
        self._client = client
        self._catalog_name = catalog_name

    @property
    def catalog_name(self) -> str:
        return self._catalog_name

    def provision_catalog(self) -> ProvisionResult:
        """Create the project catalog if it does not yet exist."""
        catalogs = cast(Any, self._client).catalogs
        try:
            catalogs.create(name=self._catalog_name)
            return ProvisionResult(full_name=self._catalog_name, created=True)
        except Exception as exc:
            if _is_already_exists(exc):
                return ProvisionResult(full_name=self._catalog_name, created=False)
            raise

    def provision_schema(self, schema_name: str) -> ProvisionResult:
        """Create a schema under the project catalog if not present."""
        schemas = cast(Any, self._client).schemas
        full = f"{self._catalog_name}.{schema_name}"
        try:
            schemas.create(name=schema_name, catalog_name=self._catalog_name)
            return ProvisionResult(full_name=full, created=True)
        except Exception as exc:
            if _is_already_exists(exc):
                return ProvisionResult(full_name=full, created=False)
            raise

    def provision_layer_schemas(
        self, schemas: tuple[str, ...] = DEFAULT_LAYER_SCHEMAS
    ) -> list[ProvisionResult]:
        """Provision all medallion layer schemas in one call."""
        return [self.provision_schema(name) for name in schemas]

    def provision_volume(
        self,
        schema_name: str,
        volume_name: str,
        volume_type: str = "MANAGED",
    ) -> ProvisionResult:
        """Create a UC volume under ``catalog.schema`` if not present.

        Volumes back the Bronze CSV landing zone (``/Volumes/{catalog}/raw/synthetic/``)
        that ``notebooks/01_bronze.py`` reads from. ``volume_type`` accepts
        either the literal string ``"MANAGED"`` / ``"EXTERNAL"`` or a
        ``databricks.sdk.service.catalog.VolumeType`` member; the value is
        resolved to the SDK enum at call time so callers don't need to import
        SDK types just to pass a constant.
        """
        volumes = cast(Any, self._client).volumes
        full = f"{self._catalog_name}.{schema_name}.{volume_name}"
        resolved_type: Any = volume_type
        if isinstance(volume_type, str):
            try:
                from databricks.sdk.service.catalog import VolumeType

                resolved_type = VolumeType(volume_type)
            except (ImportError, ValueError):  # pragma: no cover — fallback for tests
                resolved_type = volume_type
        try:
            volumes.create(
                catalog_name=self._catalog_name,
                schema_name=schema_name,
                name=volume_name,
                volume_type=resolved_type,
            )
            return ProvisionResult(full_name=full, created=True)
        except Exception as exc:
            if _is_already_exists(exc):
                return ProvisionResult(full_name=full, created=False)
            raise

    def register_external_delta_table(
        self,
        schema_name: str,
        table_name: str,
        storage_location: str,
    ) -> ProvisionResult:
        """Register an external Delta table backed by ``storage_location``.

        Used when the local-first Polars + delta-rs path has already written
        the Delta table to cloud storage and we just need UC to know about it.
        """
        tables = cast(Any, self._client).tables
        full = f"{self._catalog_name}.{schema_name}.{table_name}"
        try:
            tables.create(
                name=table_name,
                catalog_name=self._catalog_name,
                schema_name=schema_name,
                table_type="EXTERNAL",
                data_source_format="DELTA",
                storage_location=storage_location,
            )
            return ProvisionResult(full_name=full, created=True)
        except Exception as exc:
            if _is_already_exists(exc):
                return ProvisionResult(full_name=full, created=False)
            raise

    def provision_full_lakehouse(
        self,
        external_locations: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, ProvisionResult]:
        """End-to-end: catalog + 3 schemas + (optionally) external Delta tables.

        ``external_locations`` maps ``schema_name -> {table_name: storage_location}``.
        Pass ``None`` to skip external-table registration (notebooks-managed mode).
        """
        results: dict[str, ProvisionResult] = {}
        results["catalog"] = self.provision_catalog()
        for schema_result in self.provision_layer_schemas():
            results[f"schema:{schema_result.full_name}"] = schema_result
        if external_locations:
            for schema_name, tables in external_locations.items():
                for table_name, location in tables.items():
                    res = self.register_external_delta_table(
                        schema_name=schema_name,
                        table_name=table_name,
                        storage_location=location,
                    )
                    results[f"table:{res.full_name}"] = res
        return results
