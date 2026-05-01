# Databricks notebook source
# MAGIC %md
# MAGIC # Gold marts — RWA aggregation + DQ scorecard
# MAGIC
# MAGIC PySpark variant of `src/bcbs239_lakehouse/pipeline/gold.py`.
# MAGIC
# MAGIC **Outputs:**
# MAGIC * `{catalog}.gold.fact_rwa_aggregation` — RWA rollup by entity / type / period
# MAGIC * `{catalog}.gold.fact_dq_scorecard` — 4 BCBS 239 DQ dimensions per source per snapshot
# MAGIC
# MAGIC The DQ scorecard mart is what `notebooks/04_dashboard.py` (the Lakeview
# MAGIC publisher) binds to.

# COMMAND ----------

CATALOG = "bcbs239_lakehouse"
SILVER_SCHEMA = "silver"
GOLD_SCHEMA = "gold"

# COMMAND ----------

from pyspark.sql import functions as F

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_rwa_aggregation

# COMMAND ----------

exposure = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.exposure")  # noqa: F821
rwa = (
    exposure.withColumn("rwa_eur", F.col("amount_eur") * F.col("risk_weight"))
    .groupBy("lei", "exposure_type", "as_of_date")
    .agg(
        F.count("*").alias("exposure_count"),
        F.sum("amount_eur").alias("total_amount_eur"),
        F.sum("rwa_eur").alias("total_rwa_eur"),
    )
    .orderBy("lei", "exposure_type", "as_of_date")
)
(
    rwa.write.format("delta")
    .mode("overwrite")
    .saveAsTable(f"{CATALOG}.{GOLD_SCHEMA}.fact_rwa_aggregation")
)
print(f"gold.fact_rwa_aggregation: {rwa.count()} rows")  # noqa: T201

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_dq_scorecard
# MAGIC
# MAGIC Inline implementation of the 4 BCBS 239 DQ scorers. Mirror of
# MAGIC `bcbs239_lakehouse.quality.dimensions` in PySpark form.

# COMMAND ----------

from datetime import datetime, timezone

snapshot_ts = datetime.now(tz=timezone.utc)

scorecard_rows: list[dict[str, object]] = []


def _record(source: str, dimension: str, sample: int, failed: int) -> None:
    score = 1.0 - (failed / sample) if sample > 0 else 1.0
    scorecard_rows.append(
        {
            "snapshot_ts": snapshot_ts,
            "source": source,
            "dimension": dimension,
            "score": float(score),
            "sample_size": int(sample),
            "failed_count": int(failed),
        }
    )


# completeness — required-field non-null counts
COMPLETENESS_REQUIRED = {
    "counterparty": ["lei", "legal_name", "country_iso2", "sector"],
    "exposure": ["exposure_id", "lei", "amount_eur", "risk_weight", "as_of_date"],
    "collateral": ["collateral_id", "exposure_id", "value_eur", "valuation_date"],
}

for source, fields in COMPLETENESS_REQUIRED.items():
    df = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.{source}")  # noqa: F821
    sample = df.count()
    bad_filter = None
    for f in fields:
        cond = F.col(f).isNull()
        bad_filter = cond if bad_filter is None else bad_filter | cond
    failed = df.filter(bad_filter).count() if bad_filter is not None and sample > 0 else 0
    _record(source, "completeness", sample, failed)

# integrity — natural-key uniqueness
NATURAL_KEYS = {
    "counterparty": ["lei"],
    "exposure": ["exposure_id"],
    "collateral": ["collateral_id"],
}
for source, keys in NATURAL_KEYS.items():
    df = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.{source}")  # noqa: F821
    sample = df.count()
    distinct = df.select(*keys).distinct().count()
    failed = sample - distinct
    _record(source, "integrity", sample, failed)

# accuracy — exposure.risk_weight in [0, 1.5]; collateral.haircut_pct in [0, 1]
df = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.exposure")  # noqa: F821
sample = df.count()
failed = df.filter((F.col("risk_weight") < 0) | (F.col("risk_weight") > 1.5)).count()
_record("exposure", "accuracy", sample, failed)

df = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.collateral")  # noqa: F821
sample = df.count()
failed = df.filter((F.col("haircut_pct") < 0) | (F.col("haircut_pct") > 1)).count()
_record("collateral", "accuracy", sample, failed)

# timeliness — exposure: every as_of_date matches the latest; collateral: valuation within 180 d
df = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.exposure")  # noqa: F821
sample = df.count()
latest = df.agg(F.max("as_of_date")).collect()[0][0]
failed = df.filter(F.col("as_of_date") != F.lit(latest)).count() if latest is not None else 0
_record("exposure", "timeliness", sample, failed)

df = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.collateral")  # noqa: F821
sample = df.count()
latest = df.agg(F.max("valuation_date")).collect()[0][0]
failed = df.filter(F.datediff(F.lit(latest), F.col("valuation_date")) > 180).count() if latest is not None else 0
_record("collateral", "timeliness", sample, failed)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Persist scorecard

# COMMAND ----------

from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

scorecard_schema = StructType(
    [
        StructField("snapshot_ts", TimestampType(), False),
        StructField("source", StringType(), False),
        StructField("dimension", StringType(), False),
        StructField("score", DoubleType(), False),
        StructField("sample_size", LongType(), False),
        StructField("failed_count", LongType(), False),
    ]
)

scorecard_df = spark.createDataFrame(scorecard_rows, schema=scorecard_schema)  # noqa: F821
(
    scorecard_df.write.format("delta")
    .mode("append")
    .saveAsTable(f"{CATALOG}.{GOLD_SCHEMA}.fact_dq_scorecard")
)
print(f"gold.fact_dq_scorecard: appended {scorecard_df.count()} rows")  # noqa: T201

# COMMAND ----------

# MAGIC %md
# MAGIC ## Inline scorecard preview

# COMMAND ----------

display(  # noqa: F821
    spark.table(f"{CATALOG}.{GOLD_SCHEMA}.fact_dq_scorecard")  # noqa: F821
    .filter(F.col("snapshot_ts") == F.lit(snapshot_ts))
    .orderBy("source", "dimension")
)
