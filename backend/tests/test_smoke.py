"""Skeleton smoke test.

Confirms the package and its four subpackages import cleanly, so the gate
has something real to run against before Phase 1.2 / 2.x fill them in.
"""

import importlib

import foghorn


def test_version_present() -> None:
    assert foghorn.__version__ == "0.0.0"


def test_subpackages_import() -> None:
    for name in ("scrapers", "ingest", "repo", "api"):
        module = importlib.import_module(f"foghorn.{name}")
        assert module is not None
