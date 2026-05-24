"""Tests for performer-name canonicalization."""

from __future__ import annotations

import pytest

from foghorn.ingest.pipeline import canonicalize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Joshua Redman Quartet", "joshua redman quartet"),
        ("  MILES   Davis  ", "miles davis"),  # case + collapsed whitespace
        ("Café Tacvba", "cafe tacvba"),  # accent stripped via NFKD
        ("Antônio Carlos Jobim", "antonio carlos jobim"),
        ("Earth, Wind & Fire", "earth wind fire"),  # punctuation -> separator
        ("Sun Ra Arkestra!", "sun ra arkestra"),
        ("Thelonious Monk (Trio)", "thelonious monk trio"),
        ("Redman, Joshua", "redman joshua"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_canonicalize(raw: str, expected: str) -> None:
    assert canonicalize(raw) == expected


def test_canonicalize_is_idempotent() -> None:
    once = canonicalize("Café  Tacvba, & Friends!")
    assert canonicalize(once) == once


def test_punctuation_does_not_merge_tokens() -> None:
    # The ampersand sits between words with no surrounding space; it must not
    # glue "wind" and "fire" together.
    assert canonicalize("Wind&Fire") == "wind fire"
