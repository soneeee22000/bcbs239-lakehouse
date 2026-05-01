# Portability — Databricks ↔ Snowflake equivalence

bcbs239-lakehouse is built on Databricks + Delta Lake + Unity Catalog + dbt-databricks. French G-SIBs run heterogeneous data stacks (BNP, SocGen, BPCE, CA all run _both_ Snowflake AND Databricks across different programs), so this document captures the layer-by-layer mapping a Snowflake-stack team would need to lift the same architecture onto their platform.

The library code (`src/bcbs239_lakehouse/`) is already platform-agnostic — Polars + delta-rs writes Delta tables that Snowflake's external-table reader and Databricks' native runtime both consume. The Databricks-specific pieces are isolated in `src/bcbs239_lakehouse/databricks/` and mirrored row-for-row below.

## Layer-by-layer equivalence matrix

| Concern                 | Databricks (this repo)                                | Snowflake equivalent                                                  | Notes                                                                                                                                                |
| ----------------------- | ----------------------------------------------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Compute substrate       | Databricks Community Edition                          | Snowflake free trial / Standard warehouse                             | Both run the demo at zero cost                                                                                                                       |
| Catalog / metastore     | **Unity Catalog**                                     | **Snowflake Horizon Catalog** (was Information Schema + Object Tags)  | UC's lineage views map to Horizon's `ACCESS_HISTORY` + `OBJECT_DEPENDENCIES`                                                                         |
| Storage format          | **Delta Lake** (`io.delta`)                           | **Iceberg** (Snowflake-managed) or **External Delta**                 | Snowflake reads Delta tables natively as external tables since 2024 — zero data movement                                                             |
| Bronze ingestion        | **Auto Loader** (`cloudFiles` source)                 | **Snowpipe** (continuous COPY INTO)                                   | Both idempotent, both checkpoint-based; same exactly-once contract                                                                                   |
| Bronze landing pattern  | `cloudFiles.format` + checkpoint                      | `COPY INTO ... FILE_FORMAT = (...)` + `STORAGE_INTEGRATION`           | Locally we replicate both with the `_ingest_log` Delta table                                                                                         |
| Silver transformation   | Spark SQL / PySpark notebooks                         | Snowflake SQL stored procedures or Snowpark Python                    | Library code (Polars) is the same; only the runtime adapter changes                                                                                  |
| Gold modelling          | **dbt-databricks 1.9**                                | **dbt-snowflake 1.9**                                                 | The `dbt_project/` SQL is 95% portable — only the `target` config changes                                                                            |
| Lineage capture         | UC `system.access.lineage` views                      | Horizon `ACCESS_HISTORY` + `OBJECT_DEPENDENCIES`                      | Both auto-populate; both expose REST APIs for graph extraction                                                                                       |
| DQ checkpoints          | Great Expectations on PySpark or Lakehouse Monitoring | Great Expectations on Snowpark or Snowflake `DATA QUALITY MONITORING` | Same expectation suites work either way                                                                                                              |
| Row-level access policy | UC row filters + column masks                         | Snowflake row access policies + masking policies                      | Syntax differs; semantics identical for BCBS 239 group-based access                                                                                  |
| Dashboard               | **Lakeview** (Databricks-native)                      | **Snowflake Dashboards** or Streamlit-in-Snowflake                    | Lakeview JSON has no direct Snowflake import; would need re-build                                                                                    |
| Orchestration           | Databricks Workflows                                  | Snowflake Tasks + Streams                                             | This project intentionally has no in-warehouse orchestration (sibling [csrd-lake](https://github.com/soneeee22000/csrd-lake) owns the Airflow story) |
| Egress to BI            | SQL Warehouse (Serverless)                            | Snowflake Standard / Enterprise warehouse                             | Both expose JDBC/ODBC; cost models differ                                                                                                            |

## Specific code paths to swap

### Bronze ingestion

```python
# Databricks (notebooks/bronze.ipynb)
df = (spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.schemaLocation", checkpoint_path)
        .load(source_dir))
df.writeStream.format("delta").outputMode("append").start(bronze_path)

# Snowflake equivalent
# CREATE PIPE ... AS COPY INTO bronze.counterparty
#   FROM @stage_csrd/counterparty/
#   FILE_FORMAT = (TYPE = CSV PARSE_HEADER = TRUE)
#   PATTERN = '.*[.]csv';
```

### Unity Catalog → Horizon

```python
# Databricks (this repo: src/bcbs239_lakehouse/databricks/unity_catalog.py)
client.catalogs.create(name="bcbs239_lakehouse")
client.schemas.create(name="bronze", catalog_name="bcbs239_lakehouse")

# Snowflake equivalent
# CREATE DATABASE bcbs239_lakehouse;
# CREATE SCHEMA bcbs239_lakehouse.bronze;
# Lineage queries: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES;
```

### Lakeview → Snowflake Dashboards

Lakeview's `serialized_dashboard` JSON does not import into Snowflake Dashboards directly. Two options:

1. Rebuild manually in Snowflake's dashboard UI (10-15 min per dashboard for the 5-widget DQ scorecard)
2. Build a Streamlit-in-Snowflake app reading from `gold.fact_dq_scorecard` — same code structure as the [csrd-lake Next.js dashboard](https://github.com/soneeee22000/csrd-lake/tree/main/dashboard)

### dbt project

The dbt project is the most portable layer. Swap:

```yaml
# dbt_project/profiles.yml — Databricks
bcbs239_lakehouse:
  target: dev
  outputs:
    dev:
      type: databricks
      catalog: bcbs239_lakehouse
      schema: gold
      ...

# Snowflake equivalent
bcbs239_lakehouse:
  target: dev
  outputs:
    dev:
      type: snowflake
      database: BCBS239_LAKEHOUSE
      schema: GOLD
      ...
```

The model SQL (`dbt_project/models/`) needs zero changes for the marts — Snowflake and Databricks SQL are functionally equivalent for `GROUP BY` aggregations. Custom data tests may need `QUALIFY` → `ROW_NUMBER() OVER` rewrites depending on the Snowflake account version.

## Things that DO NOT port

- **Auto Loader's schema evolution** — Snowpipe handles schema changes via separate `ALTER TABLE` statements
- **Lakeview JSON** — manual rebuild required
- **Lakehouse Monitoring** (Databricks-native DQ) — replace with Snowflake Data Metric Functions or Great Expectations
- **UC row filters with Python UDF** — Snowflake row access policies are SQL-only

## Why this matters for the BCBS 239 use case

Risk Data Offices at G-SIBs almost always run hybrid stacks. The team that builds the BCBS 239 evidence layer needs to understand both. Reading this matrix in interview is itself a credibility signal — most BCBS 239 demos lock to one platform and pretend portability is hand-wave. This one isn't.

## See also

- [csrd-lake](https://github.com/soneeee22000/csrd-lake) — the sibling project on the Snowflake stack (CSRD/ESRS disclosure pipeline). Pair lets a recruiter pitch the same engineer to either Databricks or Snowflake briefs.
- [ADR-001](ADR/ADR-001-delta-rs-for-library-path.md) — why this repo's library path uses delta-rs rather than PySpark + delta-spark.
