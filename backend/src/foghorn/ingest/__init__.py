"""Ingest pipeline.

Normalizes scraper output (timezone resolution, performer-name
canonicalization), dedupes against existing rows on the natural key, and
persists via the repo layer. Filled in starting Phase 1.2.
"""
