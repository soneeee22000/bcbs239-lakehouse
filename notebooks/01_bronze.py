# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze ingestion — synthetic risk data → raw Delta landings
# MAGIC
# MAGIC PySpark variant of `src/bcbs239_lakehouse/pipeline/bronze.py` for the
# MAGIC Databricks-runtime path. Library code uses Polars + delta-rs locally; this
# MAGIC notebook uses native Spark + Delta against the synthetic CSVs uploaded to
# MAGIC the workspace volume.
# MAGIC
# MAGIC **Inputs:** synthetic CSVs at `/Volumes/{catalog}/raw/synthetic/`
# MAGIC **Outputs:** Bronze Delta tables at `{catalog}.bronze.{counterparty,exposure,collateral}`

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

CATALOG = "bcbs239_lakehouse"
BRONZE_SCHEMA = "bronze"
RAW_VOLUME = f"/Volumes/{CATALOG}/raw/synthetic"

TABLES = ("counterparty", "exposure", "collateral")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Bronze ingest — read CSV as Utf8, append metadata cols, write Delta
# MAGIC
# MAGIC Bronze contract: preserve raw bytes. All columns read as STRING; Silver
# MAGIC handles the typed cast. This avoids overflow on the 20-digit synthetic LEI
# MAGIC and matches the local-path semantics in `bronze.py::ingest_bronze`.

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType


def _read_csv_as_strings(path: str) -> "DataFrame":  # noqa: F821
    """Read every CSV column as Utf8 by inferring schema then casting all to string."""
    df = spark.read.option("header", "true").csv(path)  # noqa: F821
    return df.select(*[F.col(c).cast(StringType()).alias(c) for c in df.columns])


for table in TABLES:
    src_path = f"{RAW_VOLUME}/{table}.csv"
    target_table = f"{CATALOG}.{BRONZE_SCHEMA}.{table}"
    print(f"Ingesting {src_path} -> {target_table}")  # noqa: T201
    bronze_df = (
        _read_csv_as_strings(src_path)
        .withColumn("_source_file", F.lit(f"{table}.csv"))
        .withColumn("_ingest_ts", F.current_timestamp())
    )
    (
        bronze_df.write.format("delta")
        .mode("append")
        .saveAsTable(target_table)
    )
    n = spark.table(target_table).count()  # noqa: F821
    print(f"  -> {target_table}: {n} rows total")  # noqa: T201

# COMMAND ----------

# MAGIC %md
# MAGIC ## Smoke check — non-empty Bronze tables

# COMMAND ----------

for table in TABLES:
    n = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.{table}").count()  # noqa: F821
    assert n > 0, f"Bronze table {table} is empty"
    print(f"OK {CATALOG}.{BRONZE_SCHEMA}.{table}: {n} rows")  # noqa: T201
