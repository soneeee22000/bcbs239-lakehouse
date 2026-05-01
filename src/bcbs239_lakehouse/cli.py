"""Demo orchestrator — runs synthetic -> bronze -> silver ->gold end to end.

This is the entry point ``make demo`` calls. It mirrors the contract of
the PRD Story 1 acceptance test: from a fresh clone to a populated Gold
DQ scorecard in under 15 minutes on local hardware (target on a 50-CP
synthetic dataset is ≪ 30 s).

Output is a one-screen DQ scorecard summary printed to stdout. The
on-disk artifacts at ``<root>/bronze``, ``<root>/silver``, ``<root>/gold``
are the same Delta tables a Databricks workspace would ingest natively.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import polars as pl

from bcbs239_lakehouse.data.synthetic import write_synthetic_dataset
from bcbs239_lakehouse.pipeline.bronze import ingest_bronze
from bcbs239_lakehouse.pipeline.gold import read_gold_table, run_gold
from bcbs239_lakehouse.pipeline.silver import run_silver


def run_demo(
    warehouse_root: Path,
    synthetic_dir: Path,
    n_counterparties: int = 100,
    seed: int = 42,
    cleanliness: float = 1.0,
) -> dict[str, dict[str, int]]:
    """Run synthetic -> bronze -> silver ->gold and return per-layer row counts."""
    write_synthetic_dataset(
        synthetic_dir,
        n_counterparties=n_counterparties,
        seed=seed,
        cleanliness=cleanliness,
    )

    bronze_root = warehouse_root / "bronze"
    silver_root = warehouse_root / "silver"
    gold_root = warehouse_root / "gold"

    bronze_counts = ingest_bronze(source_dir=synthetic_dir, bronze_root=bronze_root)
    silver_counts = run_silver(bronze_root=bronze_root, silver_root=silver_root)
    gold_counts = run_gold(silver_root=silver_root, gold_root=gold_root)

    return {"bronze": bronze_counts, "silver": silver_counts, "gold": gold_counts}


def _format_dq_summary(dq: pl.DataFrame) -> str:
    """Pretty-print the latest DQ snapshot as a single-screen summary."""
    if dq.is_empty():
        return "  (no DQ scorecard rows yet — Gold layer empty)"
    latest_ts = dq.get_column("snapshot_ts").max()
    latest = dq.filter(pl.col("snapshot_ts") == latest_ts).sort(["source", "dimension"])
    lines = [
        f"  snapshot_ts: {latest_ts!r}",
        "",
        f"  {'source':<14}{'dimension':<14}{'score':>8}{'sample':>10}{'failed':>10}",
        "  " + "-" * 56,
    ]
    for row in latest.iter_rows(named=True):
        lines.append(
            f"  {row['source']:<14}{row['dimension']:<14}"
            f"{row['score']:>8.3f}{row['sample_size']:>10}{row['failed_count']:>10}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the full bcbs239-lakehouse pipeline end-to-end.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("warehouse"),
        help="Local warehouse root (default: warehouse/). Contains bronze/, silver/, gold/.",
    )
    parser.add_argument(
        "--synthetic-dir",
        type=Path,
        default=Path("data/synthetic"),
        help="Where to (re)generate the synthetic CSVs.",
    )
    parser.add_argument("--counterparties", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--inject-defects",
        action="store_true",
        help="Generate the dirty-data variant (cleanliness=0.7) — PRD Story 3.",
    )
    args = parser.parse_args(argv)

    cleanliness = 0.7 if args.inject_defects else 1.0

    sys.stdout.write(
        f"\n-> bcbs239-lakehouse demo (cleanliness={cleanliness}, "
        f"counterparties={args.counterparties}, seed={args.seed})\n"
    )
    sys.stdout.write(f"-> warehouse:    {args.root.resolve()}\n")
    sys.stdout.write(f"-> synthetic:    {args.synthetic_dir.resolve()}\n\n")

    counts = run_demo(
        warehouse_root=args.root,
        synthetic_dir=args.synthetic_dir,
        n_counterparties=args.counterparties,
        seed=args.seed,
        cleanliness=cleanliness,
    )

    sys.stdout.write("-- Layer row counts ------------------------------------------\n")
    for layer, layer_counts in counts.items():
        sys.stdout.write(f"  {layer:<8} ")
        sys.stdout.write(", ".join(f"{k}={v}" for k, v in layer_counts.items()))
        sys.stdout.write("\n")

    sys.stdout.write("\n-- DQ scorecard (latest snapshot) ----------------------------\n")
    dq = read_gold_table(args.root / "gold", "fact_dq_scorecard")
    sys.stdout.write(_format_dq_summary(dq) + "\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
