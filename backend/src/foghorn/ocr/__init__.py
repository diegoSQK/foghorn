"""Pluggable OCR engines for flyer-only venues.

An OCR engine is a callable ``(image_bytes) -> list[OcrLine]`` returning
text observations with normalized bounding boxes (origin bottom-left,
Vision's convention — every engine converts to it). Scrapers depend only on
this contract, so foghorn isn't locked to any one engine: hosting on Linux
or open-sourcing swaps the engine, not the scrapers.

Engines (each a lazily-imported submodule exposing ``recognize``):

- ``apple_vision`` — macOS's built-in Vision framework. Best quality
  observed (clean word spacing); zero extra models. The default on darwin.
- ``rapidocr`` — RapidOCR (ONNX PP-OCR), pip-installable anywhere via the
  ``rapidocr`` extra (``pip install .[rapidocr]``). The default elsewhere.
  Known caveat on flyer fonts: inter-word spaces are often lost
  ("RainbowCityPark"), which degrades act-name quality and therefore
  watchlist token matching — parsers tolerate it structurally (dates,
  times, commas survive), but prefer apple_vision where available.

Selection: ``get_engine()`` honors the ``FOGHORN_OCR_ENGINE`` env var
("apple_vision" | "rapidocr"), defaulting by platform. A missing engine
dependency raises a clear RuntimeError with the install hint; per-venue
scrape errors surface in ``/api/health/scrape``.
"""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Callable
from typing import NamedTuple

ENGINE_ENV_VAR = "FOGHORN_OCR_ENGINE"
_ENGINE_MODULES = ("apple_vision", "rapidocr")


class OcrLine(NamedTuple):
    """One OCR text observation: string + normalized bounding box (origin
    bottom-left)."""

    text: str
    x: float
    y: float
    w: float
    h: float

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


OcrEngine = Callable[[bytes], list[OcrLine]]


def get_engine(name: str | None = None) -> OcrEngine:
    """Resolve an OCR engine by name, the ``FOGHORN_OCR_ENGINE`` env var, or
    the platform default (apple_vision on macOS, rapidocr elsewhere)."""
    resolved = (
        name
        or os.environ.get(ENGINE_ENV_VAR)
        or ("apple_vision" if sys.platform == "darwin" else "rapidocr")
    )
    if resolved not in _ENGINE_MODULES:
        raise RuntimeError(
            f"unknown OCR engine {resolved!r}; valid: {', '.join(_ENGINE_MODULES)}"
        )
    module = importlib.import_module(f"foghorn.ocr.{resolved}")
    recognize: OcrEngine = module.recognize
    return recognize
