"""RapidOCR engine (cross-platform; the ``rapidocr`` extra).

ONNX PP-OCR via ``rapidocr-onnxruntime`` — pip-installable on any
platform, no system binaries, models bundled. Pixel-space quad boxes are
converted to the shared normalized bottom-left ``OcrLine`` space.

Validated against the July 2026 Little Hill flyer: all rows detected with
correct geometry, but inter-word spaces are often dropped on flyer fonts
("RainbowCityPark") — structure (dates/times/commas) survives, act-name
fidelity degrades. Prefer apple_vision on macOS.
"""

from __future__ import annotations

import importlib
from typing import Any

from foghorn.ocr import OcrLine

# Observations below this confidence are noise (logo art, textures).
MIN_CONFIDENCE = 0.6

_engine: Any = None


def _get_engine() -> Any:
    global _engine
    if _engine is None:
        try:
            rapidocr = importlib.import_module("rapidocr_onnxruntime")
        except ImportError as exc:  # pragma: no cover - depends on extras
            raise RuntimeError(
                "the rapidocr OCR engine needs the 'rapidocr' extra: "
                "pip install 'foghorn[rapidocr]' (from backend/)"
            ) from exc
        _engine = rapidocr.RapidOCR()  # loads models once; reused across calls
    return _engine


def recognize(image_bytes: bytes) -> list[OcrLine]:
    """Run RapidOCR over image bytes."""
    engine = _get_engine()
    cv2 = importlib.import_module("cv2")  # rapidocr dependency
    np = importlib.import_module("numpy")  # rapidocr dependency
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("image bytes are not decodable")
    height, width = image.shape[:2]

    result, _elapsed = engine(image)
    lines: list[OcrLine] = []
    for box, text, score in result or []:
        if float(score) < MIN_CONFIDENCE:
            continue
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        lines.append(
            OcrLine(
                text=str(text),
                x=min(xs) / width,
                y=1 - max(ys) / height,
                w=(max(xs) - min(xs)) / width,
                h=(max(ys) - min(ys)) / height,
            )
        )
    return lines
