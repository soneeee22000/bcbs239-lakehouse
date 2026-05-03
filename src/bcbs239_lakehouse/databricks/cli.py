"""CLI driver for idempotent Unity Catalog provisioning.

Run as ``python -m bcbs239_lakehouse.databricks.cli provision`` (or via
``make uc-provision``). Reads ``DATABRICKS_HOST`` / ``DATABRICKS_TOKEN`` /
``DATABRICKS_CATALOG`` from ``.env`` and creates:

* the project catalog (``bcbs239_lakehouse``)
* the medallion schemas (``bronze``, ``silver``, ``gold``)
* the ``raw`` schema and the ``raw.synthetic`` managed volume backing the
  Bronze CSV landing zone read by ``notebooks/01_bronze.py``.

All operations are idempotent — re-running on a provisioned workspace prints
``exists`` for each resource and exits zero.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

from .lakeview import LakeviewPublisher
from .unity_catalog import UnityCatalogProvisioner

if TYPE_CHECKING:
    from collections.abc import Sequence


LAYER_SCHEMAS = ("bronze", "silver", "gold")
RAW_SCHEMA = "raw"
RAW_VOLUME = "synthetic"
SYNTHETIC_DIR = Path("data/synthetic")
SYNTHETIC_FILES = ("counterparty.csv", "exposure.csv", "collateral.csv")


def _client_from_env() -> tuple[WorkspaceClient, str]:
    """Build a WorkspaceClient + return the configured catalog name."""
    load_dotenv()
    host = os.environ.get("DATABRICKS_HOST", "").strip()
    token = os.environ.get("DATABRICKS_TOKEN", "").strip()
    if not host or not token:
        raise SystemExit(
            "DATABRICKS_HOST / DATABRICKS_TOKEN must be set in .env "
            "(see .env.example and docs/DEPLOY.md)."
        )
    catalog = os.environ.get("DATABRICKS_CATALOG", "bcbs239_lakehouse").strip()
    return WorkspaceClient(host=host, token=token), catalog


def _print_result(label: str, full_name: str, created: bool) -> None:
    state = "created" if created else "exists"
    print(f"{label:<8} {full_name}: {state}")  # noqa: T201


def _is_default_storage_error(exc: BaseException) -> bool:
    """Free-Edition workspaces require catalog creation via the UI."""
    msg = str(exc).lower()
    return any(
        token in msg for token in ("metastore storage root", "default storage", "managed location")
    )


def _catalog_exists(client: WorkspaceClient, catalog_name: str) -> bool:
    """Return True if the catalog already exists in this workspace."""
    catalogs = cast(Any, client).catalogs
    try:
        catalogs.get(name=catalog_name)
        return True
    except Exception:
        return False


def cmd_provision() -> int:
    """Provision catalog + 4 schemas + raw.synthetic volume idempotently."""
    client, catalog = _client_from_env()
    provisioner = UnityCatalogProvisioner(client=client, catalog_name=catalog)

    try:
        cat = provisioner.provision_catalog()
        _print_result("catalog", cat.full_name, cat.created)
    except Exception as exc:
        if _is_default_storage_error(exc):
            # Free Edition raises Default-Storage *before* checking existence.
            # If the catalog is already there (created via UI), treat as exists
            # and continue on to schemas + volume.
            if _catalog_exists(client, catalog):
                _print_result("catalog", catalog, False)
            else:
                print(  # noqa: T201
                    f"\n[free-edition] catalog '{catalog}' could not be auto-created.\n"
                    "  Reason: Free Edition / Default Storage requires the first "
                    "catalog to be created via the UI.\n"
                    "  Fix: open Catalog Explorer -> Create Catalog -> "
                    f"name={catalog!r} -> use Default Storage -> Create.\n"
                    "  Then re-run `make uc-provision` to create the schemas + volume.",
                    file=sys.stderr,
                )
                return 3
        else:
            raise

    for schema in LAYER_SCHEMAS:
        res = provisioner.provision_schema(schema)
        _print_result("schema", res.full_name, res.created)

    raw = provisioner.provision_schema(RAW_SCHEMA)
    _print_result("schema", raw.full_name, raw.created)

    vol = provisioner.provision_volume(RAW_SCHEMA, RAW_VOLUME)
    _print_result("volume", vol.full_name, vol.created)

    return 0


def cmd_upload(synthetic_dir: Path = SYNTHETIC_DIR) -> int:
    """Upload synthetic CSVs to ``/Volumes/{catalog}/raw/synthetic/`` (overwrite=True).

    Bronze notebook (``notebooks/01_bronze.py``) reads from this volume path.
    Re-running the upload is safe; ``files.upload`` is idempotent on overwrite.
    """
    client, catalog = _client_from_env()
    files = cast(Any, client).files
    target_root = f"/Volumes/{catalog}/{RAW_SCHEMA}/{RAW_VOLUME}"

    missing = [name for name in SYNTHETIC_FILES if not (synthetic_dir / name).exists()]
    if missing:
        print(  # noqa: T201
            f"missing synthetic CSVs in {synthetic_dir}: {missing}\n"
            "  Generate them first: `make synthetic` (or "
            "`python -m bcbs239_lakehouse.data.synthetic --output data/synthetic`).",
            file=sys.stderr,
        )
        return 4

    for name in SYNTHETIC_FILES:
        local = synthetic_dir / name
        target = f"{target_root}/{name}"
        with local.open("rb") as fh:
            files.upload(file_path=target, contents=fh, overwrite=True)
        print(f"upload   {target} ({local.stat().st_size} bytes)")  # noqa: T201
    return 0


def cmd_lakeview() -> int:
    """Publish the BCBS 239 DQ Scorecard Lakeview dashboard, idempotent."""
    client, _ = _client_from_env()
    warehouses = list(cast(Any, client).warehouses.list())
    if not warehouses:
        print(  # noqa: T201
            "no SQL warehouse found in this workspace.\n"
            "  Free Edition usually ships a 'Serverless Starter Warehouse' by default.",
            file=sys.stderr,
        )
        return 5
    warehouse_id = warehouses[0].id
    publisher = LakeviewPublisher(client=client, warehouse_id=warehouse_id)
    result = publisher.publish()
    state = "created" if result.created else "updated"
    print(  # noqa: T201
        f"dashboard {state}: '{result.display_name}' "
        f"(id={result.dashboard_id}, warehouse={warehouse_id})"
    )
    return 0


def _usage() -> None:
    print(  # noqa: T201
        "usage: python -m bcbs239_lakehouse.databricks.cli {provision|upload|lakeview}",
        file=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        _usage()
        return 2
    cmd = args[0]
    if cmd == "provision":
        return cmd_provision()
    if cmd == "upload":
        return cmd_upload()
    if cmd == "lakeview":
        return cmd_lakeview()
    print(f"unknown command: {cmd}", file=sys.stderr)  # noqa: T201
    _usage()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
