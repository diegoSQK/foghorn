"""Deterministic performer-genre bootstrap (Phase 7.4, stage 1).

Infers a performer-level genre from evidence already in the DB — no LLM, by
design: the deterministic layer ships first and becomes the validation
baseline if an LLM stage is ever taken on. Evidence per appearance, strongest
first:

- the show's ``genre_override`` (a per-show source/title-derived genre), or
- the venue's default genre when the venue has a real lean (eclectic/None
  venues contribute nothing), plus
- an unambiguous genre word in the performer's own name ("Fog City Swing"),
  counted once.

A performer is tagged only when the evidence agrees: every observation the
same bucket and either 2+ observations or a single *override-grade*
observation (a per-show genre is a claim about that exact bill; a venue lean
is weaker). Mixed evidence stays untagged — a performer gigging across jazz
and rock rooms is exactly who we shouldn't guess about.

Same write contract as the origin heuristic: tags carry
``genre_source='heuristic'``, never overwrite ``'manual'`` rows, and clear
when their evidence fades. Runnable via ``python -m foghorn.cli.tag_genres``.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass

from foghorn.ingest.pipeline import infer_genre_from_title
from foghorn.repo import performers as performers_repo


@dataclass(frozen=True)
class GenreVerdict:
    performer_id: int
    canonical_name: str
    genre: str | None  # None = evidence absent or mixed
    evidence: int  # observation count behind the verdict


def compute_verdicts(conn: sqlite3.Connection) -> list[GenreVerdict]:
    rows = conn.execute(
        """
        SELECT sp.performer_id, p.canonical_name, p.display_name,
               s.genre_override, v.genre AS venue_genre
        FROM show_performers sp
        JOIN performers p ON p.id = sp.performer_id
        JOIN shows s ON s.id = sp.show_id
        JOIN venues v ON v.id = s.venue_id
        """
    ).fetchall()

    # performer_id -> (canonical, display, [(genre, override_grade), ...])
    by_performer: dict[int, tuple[str, str, list[tuple[str, bool]]]] = {}
    for row in rows:
        entry = by_performer.setdefault(
            row["performer_id"], (row["canonical_name"], row["display_name"], [])
        )
        if row["genre_override"]:
            entry[2].append((row["genre_override"], True))
        elif row["venue_genre"] and row["venue_genre"] != "eclectic":
            entry[2].append((row["venue_genre"], False))

    verdicts: list[GenreVerdict] = []
    for performer_id, (canonical, display, observations) in by_performer.items():
        name_genre = infer_genre_from_title(display)
        if name_genre is not None:
            observations = [*observations, (name_genre, True)]
        counts = Counter(genre for genre, _ in observations)
        verdict: str | None = None
        if len(counts) == 1:  # unanimous evidence only
            [(genre, count)] = counts.items()
            has_override_grade = any(grade for _, grade in observations)
            if count >= 2 or has_override_grade:
                verdict = genre
        verdicts.append(
            GenreVerdict(
                performer_id=performer_id,
                canonical_name=canonical,
                genre=verdict,
                evidence=sum(counts.values()),
            )
        )
    return verdicts


def apply_heuristic(conn: sqlite3.Connection) -> dict[str, int]:
    """Tag performers from current evidence. Never touches
    ``genre_source='manual'`` rows; clears a stale heuristic tag whose
    evidence no longer supports a verdict. Returns summary counts."""
    counts = {"tagged": 0, "unknown": 0, "manual_kept": 0}
    for verdict in compute_verdicts(conn):
        row = conn.execute(
            "SELECT genre, genre_source FROM performers WHERE id = ?",
            (verdict.performer_id,),
        ).fetchone()
        if row is not None and row["genre_source"] == "manual":
            counts["manual_kept"] += 1
            continue
        if verdict.genre is None:
            counts["unknown"] += 1
            if row is not None and row["genre_source"] == "heuristic":
                performers_repo.set_genre(conn, verdict.canonical_name, None, "heuristic")
            continue
        counts["tagged"] += 1
        performers_repo.set_genre(conn, verdict.canonical_name, verdict.genre, "heuristic")
    conn.commit()
    return counts
