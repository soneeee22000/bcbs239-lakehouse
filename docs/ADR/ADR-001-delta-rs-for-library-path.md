# ADR-001: Use delta-rs (Polars + deltalake) for the library path; keep PySpark/Delta only for the notebooks/ path

**Date:** 2026-05-01
**Status:** Accepted
**Supersedes:** PRD §6 ("Bronze → Silver pipeline on local PySpark + Delta")

## Context

PRD §6 originally specified that the Bronze → Silver pipeline would run on local PySpark + Delta for tests, with no Databricks dependency. PRD §9 (open questions) flagged "Java install for local PySpark" as a verification item.

While verifying foundation on the user's Windows 11 dev box (Java 21 installed, PySpark importable), the first Delta round-trip via `pyspark` + `delta-spark` failed with:

```
java.io.FileNotFoundException: HADOOP_HOME and hadoop.home.dir are unset.
```

This is the classic Windows + PySpark friction: PySpark uses Hadoop file APIs which require `winutils.exe` and a `HADOOP_HOME` environment variable. Resolving it means downloading a third-party `winutils` binary, setting environment variables, and adding setup steps that diverge per OS. CI (Linux) is unaffected.

## Decision

Split the project into two execution paths:

1. **Library path (`src/bcbs239_lakehouse/`, `tests/`)** — Polars + the Rust-based `deltalake` package. No JVM, no Hadoop, no `winutils`. Runs identically on Windows / macOS / Linux. This is what `make test` and `make demo` execute.
2. **Notebook path (`notebooks/`)** — PySpark + `delta-spark` natively, intended to run on a real Databricks workspace (Community Edition for the demo). Local execution of the notebooks is out of scope; tests do NOT exercise this path.

Concretely:

- `pyspark` and `delta-spark` moved out of base dependencies into `[project.optional-dependencies] spark = [...]`
- `deltalake>=0.20.0` and `polars>=1.18.0` are base dependencies
- `src/bcbs239_lakehouse/pipeline/bronze.py` uses `polars.read_csv` + `polars.DataFrame.write_delta`; the underlying Rust `deltalake` writer produces standard Delta tables byte-compatible with Databricks Spark reads
- The `notebooks/` Bronze notebook (W1 sprint follow-up) re-implements the same logic in PySpark so the Databricks demo runs natively

## Consequences

**Positive**

- Local dev on Windows requires zero Java/Hadoop setup
- Tests run in ~12 s instead of waiting for a SparkSession startup (~30 s)
- CI runtime drops materially; no `actions/setup-java` step needed
- The same Delta table produced by `polars.write_delta` is readable by Databricks Spark — round-trip parity at the storage format level
- Demonstrates a real-world architectural pattern (local-first dev with platform-runtime parity) that maps well to interview discussion

**Negative**

- Two implementations of the same pipeline (library + notebook) — drift risk, mitigated by keeping logic small and well-tested in the library
- Library tests do NOT exercise PySpark code paths; if a Databricks-specific Spark behaviour matters (e.g., exotic schema inference), tests won't catch it. Acceptable trade-off for a portfolio piece on synthetic data.
- README and PRD §6 must be updated to reflect the dual-path architecture (done in this ADR + follow-up edit)

**Neutral**

- The `[spark]` extra is documented as "install only when running notebooks/ locally with full Spark stack"
- `delta-spark` Delta tables and `deltalake-rs` Delta tables are interchangeable on disk; no migration ever required

## Alternatives considered

1. **Install `winutils.exe` and set `HADOOP_HOME`** — requires downloading a third-party Hadoop Windows binary, not officially distributed by Apache. Adds setup friction and supply-chain risk. Rejected.
2. **Drop local Spark entirely; only run on Databricks** — would mean tests can't exercise the pipeline at all without a Databricks workspace. Rejected (tests must be runnable in CI without Databricks credentials).
3. **WSL2 inside Windows for PySpark** — works, but adds OS-level setup the user must perform. Rejected for portfolio reproducibility.

## References

- delta-rs project: <https://github.com/delta-io/delta-rs>
- Polars Delta integration: <https://docs.pola.rs/api/python/stable/reference/io.html#delta-lake>
- Databricks Auto Loader pattern (the contract this implementation honours): incremental, idempotent file ingestion with checkpointing
