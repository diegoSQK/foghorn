"""foghorn backend — Bay Area music & jazz show aggregator.

Package layout (filled in over Phase 1.2 / 2.x):

- ``foghorn.scrapers`` — per-venue scrapers returning typed ``ScrapedShow`` records.
- ``foghorn.ingest`` — normalize / dedupe / persist pipeline.
- ``foghorn.repo`` — SQLite persistence layer.
- ``foghorn.api`` — FastAPI HTTP surface.
"""

__all__ = ["__version__"]

__version__ = "0.0.0"
