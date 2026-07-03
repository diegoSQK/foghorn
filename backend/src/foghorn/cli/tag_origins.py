"""``make tag-origins``: run the local/touring heuristic over the default DB.

Idempotent; safe to re-run after every scrape (recurrence evidence improves as
history accumulates). Manual tags are never overwritten. Prints the tag
distribution and exits 0.
"""

from __future__ import annotations

from foghorn.repo import db
from foghorn.tagging.origin import apply_heuristic


def main() -> None:
    conn = db.connect()
    try:
        counts = apply_heuristic(conn)
    finally:
        conn.close()
    print(
        f"local={counts['local']} touring={counts['touring']} "
        f"unknown={counts['unknown']} manual_kept={counts['manual_kept']}"
    )


if __name__ == "__main__":
    main()
