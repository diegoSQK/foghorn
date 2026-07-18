"""Apple Vision OCR engine (macOS only).

``VNRecognizeTextRequest`` at accurate level with language correction —
ships with the OS, no service, no model download. The pyobjc bridges are
darwin-marked dependencies and imported lazily, so this module is
importable (and the registry can name it) on any platform; calling
``recognize`` off-macOS raises with a pointer at the alternatives.
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

from foghorn.ocr import OcrLine


def recognize(image_bytes: bytes) -> list[OcrLine]:
    """Run Vision text recognition over image bytes."""
    if sys.platform != "darwin":
        raise RuntimeError(
            "the apple_vision OCR engine needs macOS; install the rapidocr "
            "extra and set FOGHORN_OCR_ENGINE=rapidocr on other platforms"
        )
    Foundation = importlib.import_module("Foundation")
    Quartz = importlib.import_module("Quartz")
    Vision = importlib.import_module("Vision")

    data = Foundation.NSData.dataWithBytes_length_(image_bytes, len(image_bytes))
    source = Quartz.CGImageSourceCreateWithData(data, None)
    if source is None:
        raise RuntimeError("image bytes are not decodable")
    image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)

    lines: list[OcrLine] = []

    # ``Any``: the request is a pyobjc proxy whose attributes mypy can't see
    # (and whose availability is darwin-only anyway).
    def handler(request: Any, _error: object) -> None:
        for obs in request.results():
            box = obs.boundingBox()
            lines.append(
                OcrLine(
                    text=str(obs.topCandidates_(1)[0].string()),
                    x=float(box.origin.x),
                    y=float(box.origin.y),
                    w=float(box.size.width),
                    h=float(box.size.height),
                )
            )

    request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(
        handler
    )
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    handler_obj = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        image, None
    )
    ok, error = handler_obj.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(f"Vision text recognition failed: {error}")
    return lines
