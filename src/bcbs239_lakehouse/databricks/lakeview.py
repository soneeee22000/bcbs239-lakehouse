"""Lakeview dashboard provisioning for the BCBS 239 DQ scorecard.

Wraps ``databricks-sdk`` Lakeview APIs to publish (or update) the
``BCBS 239 DQ Scorecard`` dashboard from a JSON specification stored in
``src/bcbs239_lakehouse/databricks/dashboards/``. The dashboard is bound
to the Gold ``fact_dq_scorecard`` Delta table provisioned in Unity Catalog
by :mod:`bcbs239_lakehouse.databricks.unity_catalog`.

The module is intentionally thin — Lakeview's serialised-dashboard JSON
is the source of truth, this code is only the upload mechanism. Tests
exercise the upload contract via mocks; visual rendering is verified
manually on the live Databricks workspace before recording the demo GIF.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:  # pragma: no cover
    from databricks.sdk import WorkspaceClient


DASHBOARD_NAME = "BCBS 239 DQ Scorecard"
DEFAULT_SPEC_PATH = Path(__file__).parent / "dashboards" / "dq_scorecard.json"


@dataclass(frozen=True)
class DashboardResult:
    """Outcome of an idempotent dashboard publish call."""

    dashboard_id: str
    display_name: str
    created: bool  # True = newly created; False = updated existing


class LakeviewPublisher:
    """Publish or update the DQ scorecard Lakeview dashboard."""

    def __init__(self, client: WorkspaceClient, warehouse_id: str) -> None:
        self._client = client
        self._warehouse_id = warehouse_id

    @property
    def warehouse_id(self) -> str:
        return self._warehouse_id

    def _load_spec(self, spec_path: Path) -> str:
        if not spec_path.exists():
            raise FileNotFoundError(f"Lakeview spec not found: {spec_path}")
        # Round-trip through json to validate parseability before upload.
        return json.dumps(json.loads(spec_path.read_text(encoding="utf-8")))

    def _find_existing_dashboard_id(self, display_name: str) -> str | None:
        """Look up an existing Lakeview dashboard by display name."""
        lakeview = cast(Any, self._client).lakeview
        for dashboard in lakeview.list():
            if getattr(dashboard, "display_name", None) == display_name:
                dashboard_id = getattr(dashboard, "dashboard_id", None)
                if isinstance(dashboard_id, str):
                    return dashboard_id
        return None

    def _build_dashboard(self, display_name: str, serialized: str) -> Any:
        """Wrap the dashboard fields in the SDK's Dashboard dataclass.

        Imported lazily so unit tests can mock the SDK without installing it.
        """
        from databricks.sdk.service.dashboards import Dashboard

        return Dashboard(
            display_name=display_name,
            serialized_dashboard=serialized,
            warehouse_id=self._warehouse_id,
        )

    def publish(
        self,
        display_name: str = DASHBOARD_NAME,
        spec_path: Path = DEFAULT_SPEC_PATH,
    ) -> DashboardResult:
        """Create or update the named dashboard from a JSON spec on disk."""
        serialized = self._load_spec(spec_path)
        lakeview = cast(Any, self._client).lakeview
        existing_id = self._find_existing_dashboard_id(display_name)
        dashboard = self._build_dashboard(display_name, serialized)
        if existing_id is None:
            response = lakeview.create(dashboard)
            dashboard_id = getattr(response, "dashboard_id", "") or ""
            return DashboardResult(
                dashboard_id=dashboard_id,
                display_name=display_name,
                created=True,
            )
        lakeview.update(existing_id, dashboard)
        return DashboardResult(
            dashboard_id=existing_id,
            display_name=display_name,
            created=False,
        )
