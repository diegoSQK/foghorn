"""``make tag-genres``: run the deterministic performer-genre bootstrap.

Idempotent; safe after every scrape. Manual tags are never overwritten.
Prints the tag distribution and exits 0.
"""

from __future__ import annotations

from foghorn.repo import db
from foghorn.tagging.genre import apply_heuristic


def main() -> None:
    conn = db.connect()
    try:
        counts = apply_heuristic(conn)
        top = conn.execute(
            "SELECT genre, COUNT(*) FROM performers WHERE genre IS NOT NULL "
            "GROUP BY genre ORDER BY 2 DESC"
        ).fetchall()
    finally:
        conn.close()
    print(
        f"tagged={counts['tagged']} unknown={counts['unknown']} "
        f"manual_kept={counts['manual_kept']}"
    )
    print(" ".join(f"{genre}={n}" for genre, n in top))


if __name__ == "__main__":
    main()
