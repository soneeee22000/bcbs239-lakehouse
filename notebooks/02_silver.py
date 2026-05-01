# Databricks notebook source
# MAGIC %md
# MAGIC # Silver layer — typed casts + dedup
# MAGIC
# MAGIC PySpark variant of `src/bcbs239_lakehouse/pipeline/silver.py`. Strips
# MAGIC `_source_file`, renames `_ingest_ts` to `silver_loaded_at`, casts string
# MAGIC columns to typed schema, dedupes on natural key keeping the latest
# MAGIC `silver_loaded_at` row.
# MAGIC
# MAGIC **Business-rule violations** (negative amount, future maturity, invalid
# MAGIC risk weight) are PRESERVED — Gold's DQ scorecard surfaces them.

# COMMAND ----------

CATALOG = "bcbs239_lakehouse"
BRONZE_SCHEMA = "bronze"
SILVER_SCHEMA = "silver"

# COMMAND ----------

from pyspark.sql import Window
from pyspark.sql import functions as F


def _strip_and_rename(df: "DataFrame") -> "DataFrame":  # noqa: F821
    out = df.drop("_source_file")
    return out.withColumnRenamed("_ingest_ts", "silver_loaded_at")


def _dedupe_keep_latest(df: "DataFrame", natural_key: list[str]) -> "DataFrame":  # noqa: F821
    window = Window.partitionBy(*natural_key).orderBy(F.col("silver_loaded_at").desc())
    return (
        df.withColumn("_row_n", F.row_number().over(window))
        .filter(F.col("_row_n") == 1)
        .drop("_row_n")
    )


# COMMAND ----------

# MAGIC %md
# MAGIC ## counterparty

# COMMAND ----------

bronze = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.counterparty")  # noqa: F821
silver = (
    _strip_and_rename(bronze)
    .withColumn("inception_date", F.to_date("inception_date", "yyyy-MM-dd"))
)
silver = _dedupe_keep_latest(silver, natural_key=["lei"])
(
    silver.write.format("delta")
    .mode("overwrite")
    .saveAsTable(f"{CATALOG}.{SILVER_SCHEMA}.counterparty")
)
print(f"silver.counterparty: {silver.count()} rows")  # noqa: T201

# COMMAND ----------

# MAGIC %md
# MAGIC ## exposure

# COMMAND ----------

bronze = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.exposure")  # noqa: F821
silver = (
    _strip_and_rename(bronze)
    .withColumn("amount_eur", F.col("amount_eur").cast("double"))
    .withColumn("risk_weight", F.col("risk_weight").cast("double"))
    .withColumn("internal_rating", F.col("internal_rating").cast("int"))
    .withColumn("as_of_date", F.to_date("as_of_date", "yyyy-MM-dd"))
    .withColumn("maturity_date", F.to_date("maturity_date", "yyyy-MM-dd"))
)
silver = _dedupe_keep_latest(silver, natural_key=["exposure_id"])
(
    silver.write.format("delta")
    .mode("overwrite")
    .saveAsTable(f"{CATALOG}.{SILVER_SCHEMA}.exposure")
)
print(f"silver.exposure: {silver.count()} rows")  # noqa: T201

# COMMAND ----------

# MAGIC %md
# MAGIC ## collateral

# COMMAND ----------

bronze = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.collateral")  # noqa: F821
silver = (
    _strip_and_rename(bronze)
    .withColumn("value_eur", F.col("value_eur").cast("double"))
    .withColumn("haircut_pct", F.col("haircut_pct").cast("double"))
    .withColumn("valuation_date", F.to_date("valuation_date", "yyyy-MM-dd"))
    .withColumn("pledge_date", F.to_date("pledge_date", "yyyy-MM-dd"))
)
silver = _dedupe_keep_latest(silver, natural_key=["collateral_id"])
(
    silver.write.format("delta")
    .mode("overwrite")
    .saveAsTable(f"{CATALOG}.{SILVER_SCHEMA}.collateral")
)
print(f"silver.collateral: {silver.count()} rows")  # noqa: T201
