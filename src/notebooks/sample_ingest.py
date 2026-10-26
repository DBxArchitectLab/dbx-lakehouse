# Databricks notebook source
# MAGIC %md
# MAGIC # Sample ingest
# MAGIC Writes `sample_orders` and `sample_revenue_by_region` to the bundle's schema. The catalog and schema come from the
# MAGIC job parameters, so the same notebook runs unchanged in dev, uat and prod.

# COMMAND ----------

import os
import sys

# The bundle deploys src/ next to this notebook's folder; make src/lakehouse importable.
sys.path.append(os.path.abspath(".."))

from lakehouse.sample import revenue_by_region, sample_orders  # noqa: E402

catalog = dbutils.widgets.get("catalog")  # noqa: F821 (dbutils is provided by Databricks)
schema = dbutils.widgets.get("schema")  # noqa: F821
print(f"Writing to {catalog}.{schema}")

# COMMAND ----------

orders = sample_orders(200)
spark.createDataFrame(orders).write.mode("overwrite").saveAsTable(f"{catalog}.{schema}.sample_orders")  # noqa: F821

revenue = [{"region": r, "revenue": v} for r, v in revenue_by_region(orders).items()]
spark.createDataFrame(revenue).write.mode("overwrite").saveAsTable(  # noqa: F821
    f"{catalog}.{schema}.sample_revenue_by_region")

display(spark.table(f"{catalog}.{schema}.sample_revenue_by_region"))  # noqa: F821
