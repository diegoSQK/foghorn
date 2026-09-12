"""Re-run billing-parse + surname-resolution over shows already in the DB.

``ingest_scraped_shows`` does this for every show it touches, so the nightly
scrape keeps *upcoming* shows current. Two cases it can't reach:

* **Past shows**, which no scraper returns any more. They still matter — they
  are what makes a surname *known*, and the whole resolution gate is a
  question about the catalogue.
* **Newly-unique surnames.** Resolution is a snapshot of what foghorn knew at
  ingest time. When a later show introduces the first "Larry Ochs", every
  earlier bare ``Ochs`` becomes resolvable, and nothing would revisit it.

Idempotent and additive: it never edits a billing, never touches
``headliner_canonical`` (so no show id churns and no ``event_type_overrides``
rule is orphaned), and only rewrites ``show_performers`` links. Running it
twice in a row is a no-op the second time.

Usage: ``python -m foghorn.cli.relink_performers [--dry-run]``
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter

from foghorn.ingest.billing import parse_members
from foghorn.ingest.pipeline import canonicalize
from foghorn.ingest.surnames import SurnameIndex, build_index
from foghorn.models import Performer
from foghorn.repo import db
from foghorn.repo import performers as performers_repo


def _billed_names(conn: sqlite3.Connection, show_id: int) -> list[tuple[str, str, int]]:
    """The (display_name, role, position) the *source* gave this show, i.e.
    ignoring links this tool added on a previous run."""
    return [
        (row[0], row[1], row[2])
        for row in conn.execute(
            "SELECT p.display_name, sp.role, sp.position FROM show_performers sp "
            "JOIN performers p ON p.id = sp.performer_id "
            "WHERE sp.show_id = ? AND sp.source = 'billed' ORDER BY sp.position",
            (show_id,),
        )
    ]


def relink(conn: sqlite3.Connection, *, dry_run: bool = False) -> Counter[str]:
    """Recompute parsed/inferred links for every show. Returns a tally."""
    stats: Counter[str] = Counter()
    surnames: SurnameIndex = build_index(conn)
    show_ids = [row[0] for row in conn.execute("SELECT id FROM shows ORDER BY id")]
    stats["shows"] = len(show_ids)

    for show_id in show_ids:
        billed = _billed_names(conn, show_id)
        if not billed:
            # A show whose links predate the `source` column defaulted to
            # 'billed', so this only fires for a genuinely empty bill.
            stats["skipped_no_billing"] += 1
            continue
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT performer_id FROM show_performers WHERE show_id = ?",
                (show_id,),
            )
        }
        next_position = max(position for _, _, position in billed) + 1
        additions: list[tuple[int, str, int]] = []

        for display, _role, _position in billed:
            for member in parse_members(display):
                for name, source in _member_links(member, surnames):
                    canonical = canonicalize(name)
                    if not canonical:
                        continue
                    performer = performers_repo.upsert(
                        conn,
                        Performer(display_name=name, canonical_name=canonical),
                    )
                    assert performer.id is not None
                    if performer.id in existing:
                        continue
                    existing.add(performer.id)
                    additions.append((performer.id, source, next_position))
                    next_position += 1
                    stats[source] += 1

        if additions and not dry_run:
            conn.executemany(
                "INSERT INTO show_performers "
                "(show_id, performer_id, role, position, source) "
                "VALUES (?, ?, 'support', ?, ?)",
                [(show_id, pid, pos, src) for pid, src, pos in additions],
            )
        if additions:
            stats["shows_changed"] += 1

    if not dry_run:
        conn.commit()
    return stats


def _member_links(member: str, surnames: SurnameIndex) -> list[tuple[str, str]]:
    """The (name, provenance) links one parsed member contributes."""
    links = [(member, "parsed")]
    canonical = canonicalize(member)
    if len(canonical.split()) == 1:
        resolved = surnames.resolve(canonical)
        if resolved is not None:
            links.append((resolved.display_name, "inferred"))
    return links


# One pass can't be enough by construction: parsing a billing is what *creates*
# the person a later bare surname resolves to, so the first pass mints "Larry
# Ochs" and only the second can resolve `Ochs` to him. Passes are monotonic
# (they only add links), so this terminates; the cap is a guard, not a tuning
# knob — live data converges on pass 3.
_MAX_PASSES = 5


def relink_to_fixpoint(
    conn: sqlite3.Connection, *, dry_run: bool = False
) -> tuple[Counter[str], int]:
    """Relink repeatedly until a pass changes nothing. Returns the summed
    tally and the number of passes run."""
    total: Counter[str] = Counter()
    for attempt in range(1, _MAX_PASSES + 1):
        stats = relink(conn, dry_run=dry_run)
        total["shows"] = stats["shows"]
        total["shows_changed"] += stats["shows_changed"]
        total["parsed"] += stats["parsed"]
        total["inferred"] += stats["inferred"]
        if not stats["shows_changed"] or dry_run:
            return total, attempt
    return total, _MAX_PASSES


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing (single pass)",
    )
    args = parser.parse_args()
    conn = db.connect()
    try:
        stats, passes = relink_to_fixpoint(conn, dry_run=args.dry_run)
    finally:
        conn.close()
    print(
        f"shows={stats['shows']} changed={stats['shows_changed']} "
        f"parsed_links={stats['parsed']} inferred_links={stats['inferred']} "
        f"passes={passes}"
        + (" (dry run, nothing written)" if args.dry_run else "")
    )


if __name__ == "__main__":
    main()
