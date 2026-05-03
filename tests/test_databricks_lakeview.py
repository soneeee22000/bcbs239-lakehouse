"""Tests for the Lakeview dashboard publisher (mocked databricks-sdk)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bcbs239_lakehouse.databricks.lakeview import (
    DASHBOARD_NAME,
    DEFAULT_SPEC_PATH,
    LakeviewPublisher,
)


def _client_with_lakeview() -> MagicMock:
    client = MagicMock()
    client.lakeview = MagicMock()
    return client


def test_default_spec_file_exists_and_is_valid_json() -> None:
    """The bundled JSON spec must be parseable — caught at import time."""
    import json

    assert DEFAULT_SPEC_PATH.exists(), f"missing default spec: {DEFAULT_SPEC_PATH}"
    parsed = json.loads(DEFAULT_SPEC_PATH.read_text(encoding="utf-8"))
    assert "datasets" in parsed
    assert "pages" in parsed
    # Spec must reference the Gold DQ scorecard table
    full_text = DEFAULT_SPEC_PATH.read_text(encoding="utf-8")
    assert "bcbs239_lakehouse.gold.fact_dq_scorecard" in full_text


def test_publish_creates_when_dashboard_absent() -> None:
    client = _client_with_lakeview()
    client.lakeview.list.return_value = []
    response = MagicMock()
    response.dashboard_id = "dash-001"
    client.lakeview.create.return_value = response

    publisher = LakeviewPublisher(client, warehouse_id="wh-test")
    result = publisher.publish()
    assert result.created is True
    assert result.dashboard_id == "dash-001"
    assert result.display_name == DASHBOARD_NAME

    # SDK takes a single Dashboard object (positional). We assert on its fields.
    client.lakeview.create.assert_called_once()
    dashboard = client.lakeview.create.call_args.args[0]
    assert getattr(dashboard, "display_name", None) == DASHBOARD_NAME
    assert getattr(dashboard, "warehouse_id", None) == "wh-test"
    serialized = getattr(dashboard, "serialized_dashboard", "") or ""
    assert isinstance(serialized, str)
    assert "fact_dq_scorecard" in serialized
    client.lakeview.update.assert_not_called()


def test_publish_updates_when_dashboard_present() -> None:
    client = _client_with_lakeview()
    existing = MagicMock()
    existing.display_name = DASHBOARD_NAME
    existing.dashboard_id = "dash-existing"
    client.lakeview.list.return_value = [existing]

    publisher = LakeviewPublisher(client, warehouse_id="wh-test")
    result = publisher.publish()
    assert result.created is False
    assert result.dashboard_id == "dash-existing"
    client.lakeview.create.assert_not_called()
    client.lakeview.update.assert_called_once()
    args = client.lakeview.update.call_args.args
    assert args[0] == "dash-existing"
    dashboard = args[1]
    assert getattr(dashboard, "warehouse_id", None) == "wh-test"
    assert isinstance(getattr(dashboard, "serialized_dashboard", None), str)


def test_publish_ignores_dashboards_with_other_names() -> None:
    client = _client_with_lakeview()
    other = MagicMock()
    other.display_name = "Some Other Dashboard"
    other.dashboard_id = "dash-other"
    client.lakeview.list.return_value = [other]
    response = MagicMock()
    response.dashboard_id = "dash-new"
    client.lakeview.create.return_value = response

    publisher = LakeviewPublisher(client, warehouse_id="wh-test")
    result = publisher.publish()
    assert result.created is True
    client.lakeview.create.assert_called_once()


def test_publish_raises_for_missing_spec(tmp_path: Path) -> None:
    client = _client_with_lakeview()
    publisher = LakeviewPublisher(client, warehouse_id="wh-test")
    with pytest.raises(FileNotFoundError, match="Lakeview spec not found"):
        publisher.publish(spec_path=tmp_path / "does-not-exist.json")
