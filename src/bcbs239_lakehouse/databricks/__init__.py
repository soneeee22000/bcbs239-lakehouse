"""Databricks runtime adapters — Unity Catalog provisioning + Lakeview dashboards.

Unlike the ``pipeline/`` modules (which run pure-Python on local Polars +
delta-rs), this package targets a real Databricks workspace. Tests use
``unittest.mock`` against ``databricks-sdk`` to assert correct API usage
without requiring live credentials in CI; the live demo flips Vercel-style
between local and Databricks via env vars.
"""
