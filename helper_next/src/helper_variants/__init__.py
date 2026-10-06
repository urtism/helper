"""Reusable storage, indexing, and query engine for genomic variants.

This package deliberately has no dependency on Helper or FastAPI. Host
applications supply run metadata and decide how users are authorized to access
each database.
"""

from helper_variants.indexer import index_path, index_run, index_status
from helper_variants.query import (
    list_samples, list_variants, run_summary, variant_carriers, variant_detail,
)
from helper_variants.store import SCHEMA_VERSION, connect

__all__ = [
    "SCHEMA_VERSION", "connect", "index_path", "index_run", "index_status",
    "list_samples", "list_variants", "run_summary", "variant_carriers", "variant_detail",
]
