"""Tests for token-bag performer matching (Phase 4.1)."""

from __future__ import annotations

import pytest

from foghorn.ingest.pipeline import canonicalize
from foghorn.repo.performer_match import matches_token_bag, token_match_sql


@pytest.mark.parametrize(
    ("query", "target", "expected"),
    [
        ("joshua redman", "joshua redman quartet", True),  # subset of tokens
        ("redman joshua", "joshua redman quartet", True),  # order-independent
        ("joshua redman quartet", "joshua redman quartet", True),  # itself
        ("redman", "joshua redman quartet", True),  # single token
        ("joshua redman", "joshua bell", False),  # missing a token
        ("redm", "joshua redman", False),  # partial token != whole token
        ("", "joshua redman", False),  # empty query never matches
    ],
)
def test_matches_token_bag(query: str, target: str, expected: bool) -> None:
    assert matches_token_bag(query, target) is expected


def test_matches_after_canonicalize_accents_and_punctuation() -> None:
    # "Redman, Joshua" and "Joshua Redman" both canonicalize to the same bag.
    assert matches_token_bag(canonicalize("Redman, Joshua"), canonicalize("Joshua Redman Quartet"))
    assert matches_token_bag(canonicalize("café"), canonicalize("Café Tacvba"))


def test_token_match_sql_empty_inputs() -> None:
    assert token_match_sql("p.canonical_name", []) == ("", [])
    assert token_match_sql("p.canonical_name", [[]]) == ("", [])  # empty bag skipped


def test_token_match_sql_whole_token_params() -> None:
    sql, params = token_match_sql("p.canonical_name", [["joshua", "redman"]])
    assert sql.count("LIKE ?") == 2
    assert " AND " in sql
    assert params == ["% joshua %", "% redman %"]  # space-padded => whole tokens


def test_token_match_sql_multiple_bags_are_ored() -> None:
    sql, params = token_match_sql("p.canonical_name", [["joshua"], ["kamasi"]])
    assert " OR " in sql
    assert params == ["% joshua %", "% kamasi %"]
