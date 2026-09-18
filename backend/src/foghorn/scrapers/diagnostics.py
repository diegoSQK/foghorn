"""A channel for scrapers to report things a *successful* run still lost.

``IngestResult.errors`` covers a run that broke. It has nothing to say about a
run that worked exactly as designed and still dropped a show on purpose — and
that turns out to be where the data loss lives.

`scrapers/sfjazz.scrape_center()` drops SFJAZZ's off-site dates deliberately,
because the nightly ``prune=True`` would otherwise reap the host venue's own
programming. Its docstring says those dates "arrive through the host venue's
own scraper", which is true for the Paramount and the UC Theatre and was false
for Davies — whose only source published one company's season. A Julian Lage
date vanished, and foghorn had nothing to say about it. The scraper already
warns about *unmapped* locations precisely so new programming gets a human
glance; the mapped-and-deliberately-dropped path was the one with no telemetry,
and it was the one that lost a show.

So: a note is an observation about a run, not a failure. It changes nothing
about what gets ingested, rides the existing ``scrape_runs`` record, and
surfaces on ``GET /api/health/scrape`` beside the error list.

A ``ContextVar`` rather than a plain module global because the nightly run
happens on an APScheduler background thread while ``make scrape`` runs on the
main one, and tests exercise both; per-context storage keeps one run's notes
out of another's.
"""

from __future__ import annotations

from contextvars import ContextVar

_NOTES: ContextVar[list[str] | None] = ContextVar("scraper_notes", default=None)


def reset() -> None:
    """Begin collecting for one venue's slice of a run."""
    _NOTES.set([])


def note(message: str) -> None:
    """Record something this run dropped or decided. No-op when nothing is
    collecting, so a scraper run standalone (``python -m foghorn.scrapers.x``)
    or from a test doesn't need any setup."""
    current = _NOTES.get()
    if current is not None:
        current.append(message)


def drain() -> list[str]:
    """Take the notes collected since ``reset()`` and stop collecting."""
    current = _NOTES.get() or []
    _NOTES.set(None)
    return list(current)
