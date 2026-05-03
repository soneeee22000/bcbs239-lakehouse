"""Export the bcbs239-lakehouse dashboard JSON snapshot.

Queries the Databricks SQL warehouse for row counts, the latest two
fact_dq_scorecard snapshots (T1 clean and T2 dirty), and the top RWA rows
from fact_rwa_aggregation. Writes the result to ``lib/data/snapshot.json``
which the Next.js app imports at build time — Vercel never needs Databricks
credentials.

Run from the repo root after `make refresh`:

    uv run python dashboard/scripts/export_dashboard_data.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

CATALOG = "bcbs239_lakehouse"
OUT_PATH = Path(__file__).parent.parent / "lib" / "data" / "snapshot.json"


def _q(client, warehouse_id: str, sql: str) -> list[list[str]]:
    res = client.statement_execution.execute_statement(
        warehouse_id=warehouse_id, statement=sql, wait_timeout="40s"
    )
    if res.status and str(res.status.state) != "StatementState.SUCCEEDED":
        err = res.status.error.message if res.status.error else "no detail"
        raise SystemExit(f"FAIL: {err}\nSQL: {sql}")
    return res.result.data_array or [] if res.result else []


def main() -> None:
    load_dotenv(dotenv_path=Path(".env"))
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")
    if not host or not token:
        raise SystemExit("DATABRICKS_HOST / DATABRICKS_TOKEN must be set in .env")
    client = WorkspaceClient(host=host, token=token)
    warehouse = next(iter(client.warehouses.list()))
    wh_id = warehouse.id
    print(f"using warehouse: {warehouse.name} (id={wh_id})", file=sys.stderr)

    row_counts: dict[str, dict[str, int]] = {"bronze": {}, "silver": {}, "gold": {}}
    for layer, table in [
        ("bronze", "counterparty"),
        ("bronze", "exposure"),
        ("bronze", "collateral"),
        ("silver", "counterparty"),
        ("silver", "exposure"),
        ("silver", "collateral"),
        ("gold", "fact_rwa_aggregation"),
        ("gold", "fact_dq_scorecard"),
    ]:
        rows = _q(client, wh_id, f"SELECT count(*) FROM {CATALOG}.{layer}.{table}")
        row_counts[layer][table] = int(rows[0][0])

    snap_rows = _q(
        client,
        wh_id,
        f"""
        SELECT snapshot_ts, source, dimension, score, sample_size, failed_count
        FROM {CATALOG}.gold.fact_dq_scorecard
        ORDER BY snapshot_ts, source, dimension
        """,
    )
    snapshots_by_ts: dict[str, list[dict[str, object]]] = {}
    for ts, src, dim, score, sample, failed in snap_rows:
        snapshots_by_ts.setdefault(ts, []).append(
            {
                "source": src,
                "dimension": dim,
                "score": float(score),
                "sample_size": int(sample),
                "failed_count": int(failed),
            }
        )
    sorted_ts = sorted(snapshots_by_ts.keys())
    snapshots = []
    for i, ts in enumerate(sorted_ts):
        label = "T1_clean" if i == 0 else f"T{i + 1}_dirty" if i == 1 else f"T{i + 1}"
        snapshots.append(
            {
                "snapshot_ts": ts,
                "label": label,
                "dimensions": snapshots_by_ts[ts],
            }
        )

    rwa_rows = _q(
        client,
        wh_id,
        f"""
        SELECT lei, exposure_type, as_of_date, exposure_count,
               total_amount_eur, total_rwa_eur
        FROM {CATALOG}.gold.fact_rwa_aggregation
        ORDER BY total_rwa_eur DESC
        LIMIT 25
        """,
    )
    rwa_top = [
        {
            "lei": str(lei),
            "exposure_type": str(et),
            "as_of_date": str(d),
            "exposure_count": int(ec),
            "total_amount_eur": float(amt),
            "total_rwa_eur": float(rwa),
        }
        for lei, et, d, ec, amt, rwa in rwa_rows
    ]

    snapshot = {
        "extracted_at": datetime.now(tz=UTC).isoformat(),
        "row_counts": row_counts,
        "scorecard_snapshots": snapshots,
        "rwa_top": rwa_top,
        "catalog": CATALOG,
        "synthetic": True,
        "synthetic_lei_prefix": "9999",
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(Path.cwd())} ({OUT_PATH.stat().st_size} bytes)")
    print(
        f"  layers: {sum(len(v) for v in row_counts.values())} tables, "
        f"{len(snapshots)} scorecard snapshots, "
        f"{len(rwa_top)} top RWA rows"
    )


if __name__ == "__main__":
    main()
