"""Tests for the UC provisioning CLI driver (mocked databricks-sdk)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bcbs239_lakehouse.databricks import cli


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.cloud.databricks.com")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapifake")
    monkeypatch.setenv("DATABRICKS_CATALOG", "bcbs239_lakehouse")


def _client_with_apis() -> MagicMock:
    client = MagicMock()
    client.catalogs = MagicMock()
    client.schemas = MagicMock()
    client.volumes = MagicMock()
    return client


def test_cmd_provision_creates_catalog_layer_schemas_raw_schema_and_volume(
    fake_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end: catalog + bronze/silver/gold + raw schema + synthetic volume."""
    fake_client = _client_with_apis()
    with patch.object(cli, "WorkspaceClient", return_value=fake_client):
        rc = cli.cmd_provision()
    assert rc == 0
    # 1 catalog, 4 schemas (bronze/silver/gold/raw), 1 volume
    assert fake_client.catalogs.create.call_count == 1
    assert fake_client.schemas.create.call_count == 4
    schema_names = {call.kwargs.get("name") for call in fake_client.schemas.create.call_args_list}
    assert schema_names == {"bronze", "silver", "gold", "raw"}
    assert fake_client.volumes.create.call_count == 1
    vol_kwargs = fake_client.volumes.create.call_args.kwargs
    assert vol_kwargs["schema_name"] == "raw"
    assert vol_kwargs["name"] == "synthetic"
    out = capsys.readouterr().out
    assert "bcbs239_lakehouse.raw.synthetic" in out


def test_cmd_provision_is_idempotent_on_reruns(
    fake_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """Re-running provision when everything exists must succeed and report 'exists'."""

    class _AlreadyExistsError(Exception):
        pass

    fake_client = _client_with_apis()
    fake_client.catalogs.create.side_effect = _AlreadyExistsError("Catalog already_exists")
    fake_client.schemas.create.side_effect = _AlreadyExistsError("schema already exists")
    fake_client.volumes.create.side_effect = _AlreadyExistsError("Volume AlreadyExists")
    with patch.object(cli, "WorkspaceClient", return_value=fake_client):
        rc = cli.cmd_provision()
    assert rc == 0
    out = capsys.readouterr().out
    assert "exists" in out


def test_cmd_provision_friendly_message_when_catalog_absent_on_free_edition(
    fake_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """Free-Edition + catalog absent → print UI fix and bail."""

    class _InvalidStateError(Exception):
        pass

    class _NotFoundError(Exception):
        pass

    fake_client = _client_with_apis()
    fake_client.catalogs.create.side_effect = _InvalidStateError(
        "Metastore storage root URL does not exist. Default Storage is enabled in your account."
    )
    fake_client.catalogs.get.side_effect = _NotFoundError("Catalog not found")
    with patch.object(cli, "WorkspaceClient", return_value=fake_client):
        rc = cli.cmd_provision()
    assert rc == 3
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Catalog Explorer" in combined
    fake_client.schemas.create.assert_not_called()
    fake_client.volumes.create.assert_not_called()


def test_cmd_provision_continues_when_catalog_already_created_via_ui(
    fake_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """Free-Edition + catalog already exists (UI-created) → skip catalog, do schemas + volume."""

    class _InvalidStateError(Exception):
        pass

    fake_client = _client_with_apis()
    fake_client.catalogs.create.side_effect = _InvalidStateError(
        "Metastore storage root URL does not exist. Default Storage is enabled."
    )
    fake_client.catalogs.get.return_value = MagicMock()
    with patch.object(cli, "WorkspaceClient", return_value=fake_client):
        rc = cli.cmd_provision()
    assert rc == 0
    assert fake_client.schemas.create.call_count == 4
    assert fake_client.volumes.create.call_count == 1
    out = capsys.readouterr().out
    assert "bcbs239_lakehouse: exists" in out


def test_cmd_provision_exits_when_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    # Block load_dotenv from re-hydrating env from a real .env on disk.
    monkeypatch.setattr(cli, "load_dotenv", lambda *_, **__: None)
    with pytest.raises(SystemExit, match="DATABRICKS_HOST"):
        cli.cmd_provision()


def test_cmd_upload_pushes_each_synthetic_csv_to_volume(
    fake_env: None,
    tmp_path: pytest.TempPathFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Upload writes counterparty/exposure/collateral CSVs to the UC volume."""
    synthetic_dir = tmp_path / "synthetic"  # type: ignore[operator]
    synthetic_dir.mkdir()
    for name in cli.SYNTHETIC_FILES:
        (synthetic_dir / name).write_bytes(b"col_a,col_b\n1,2\n")

    fake_client = MagicMock()
    fake_client.files = MagicMock()
    with patch.object(cli, "WorkspaceClient", return_value=fake_client):
        rc = cli.cmd_upload(synthetic_dir=synthetic_dir)

    assert rc == 0
    assert fake_client.files.upload.call_count == 3
    target_paths = {call.kwargs["file_path"] for call in fake_client.files.upload.call_args_list}
    assert target_paths == {
        "/Volumes/bcbs239_lakehouse/raw/synthetic/counterparty.csv",
        "/Volumes/bcbs239_lakehouse/raw/synthetic/exposure.csv",
        "/Volumes/bcbs239_lakehouse/raw/synthetic/collateral.csv",
    }
    for call in fake_client.files.upload.call_args_list:
        assert call.kwargs["overwrite"] is True
    out = capsys.readouterr().out
    assert "counterparty.csv" in out


def test_cmd_upload_errors_when_synthetic_csvs_missing(
    fake_env: None,
    tmp_path: pytest.TempPathFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No CSVs on disk → exit 4 with a 'run make synthetic' instruction."""
    empty = tmp_path / "empty"  # type: ignore[operator]
    empty.mkdir()
    fake_client = MagicMock()
    with patch.object(cli, "WorkspaceClient", return_value=fake_client):
        rc = cli.cmd_upload(synthetic_dir=empty)
    assert rc == 4
    fake_client.files.upload.assert_not_called()
    err = capsys.readouterr().err
    assert "make synthetic" in err or "data.synthetic" in err


def test_cmd_lakeview_publishes_via_first_available_warehouse(
    fake_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """Lakeview command discovers the SQL warehouse and calls publisher.publish()."""
    fake_client = MagicMock()
    warehouse = MagicMock()
    warehouse.id = "wh-test-1"
    fake_client.warehouses.list.return_value = [warehouse]

    fake_publisher = MagicMock()
    publish_result = MagicMock()
    publish_result.dashboard_id = "dash-bcbs239-1"
    publish_result.display_name = "BCBS 239 DQ Scorecard"
    publish_result.created = True
    fake_publisher.publish.return_value = publish_result

    with (
        patch.object(cli, "WorkspaceClient", return_value=fake_client),
        patch.object(cli, "LakeviewPublisher", return_value=fake_publisher) as pub_ctor,
    ):
        rc = cli.cmd_lakeview()
    assert rc == 0
    pub_ctor.assert_called_once()
    assert pub_ctor.call_args.kwargs["warehouse_id"] == "wh-test-1"
    fake_publisher.publish.assert_called_once()
    out = capsys.readouterr().out
    assert "BCBS 239 DQ Scorecard" in out
    assert "dash-bcbs239-1" in out


def test_cmd_lakeview_errors_when_no_warehouse_present(
    fake_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """Free-Edition workspaces normally ship a starter warehouse; if absent, give a hint."""
    fake_client = MagicMock()
    fake_client.warehouses.list.return_value = []
    with patch.object(cli, "WorkspaceClient", return_value=fake_client):
        rc = cli.cmd_lakeview()
    assert rc == 5
    err = capsys.readouterr().err
    assert "warehouse" in err.lower()


def test_main_dispatches_to_provision(fake_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "cmd_provision", lambda: 0)
    assert cli.main(["provision"]) == 0


def test_main_dispatches_to_upload(fake_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "cmd_upload", lambda: 0)
    assert cli.main(["upload"]) == 0


def test_main_dispatches_to_lakeview(fake_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "cmd_lakeview", lambda: 0)
    assert cli.main(["lakeview"]) == 0


def test_main_returns_usage_for_unknown_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = cli.main(["bogus"])
    assert rc == 2
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "usage" in combined or "unknown" in combined


def test_main_returns_usage_when_no_args(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = cli.main([])
    assert rc == 2
