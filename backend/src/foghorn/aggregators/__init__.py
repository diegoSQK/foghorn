"""Aggregator ingest sources (multi-venue, unlike per-venue scrapers).

An aggregator yields events *across* venues, so it can't live in
``REGISTERED_SCRAPERS`` (which maps one venue slug to one scrape callable).
``AGGREGATOR_SOURCES`` maps a source id to a zero-argument callable returning
``list[AggregatedEvent]``; the scheduler runs them after the venue scrapers
and ``aggregators.ingest`` resolves each event's venue (matching existing
venues by token overlap, else auto-creating a quarantined
``source='aggregator'`` venue) with a fuzzy duplicate guard against
venue-scraped shows.
"""

from __future__ import annotations

from collections.abc import Callable

from foghorn.aggregators.models import AggregatedEvent


def _bay_improviser() -> list[AggregatedEvent]:
    from foghorn.aggregators import bay_improviser

    return bay_improviser.scrape()


def _sf_symphony() -> list[AggregatedEvent]:
    from foghorn.aggregators import sf_symphony

    return sf_symphony.scrape()


def _sf_philharmonic() -> list[AggregatedEvent]:
    from foghorn.aggregators import sf_philharmonic

    return sf_philharmonic.scrape()


AGGREGATOR_SOURCES: dict[str, Callable[[], list[AggregatedEvent]]] = {
    "bay_improviser": _bay_improviser,
    # Group feeds: performing ensembles whose events name the hall they play
    # (groups are performers, not venues — see aggregators/sf_symphony).
    "sf_symphony": _sf_symphony,
    "sf_philharmonic": _sf_philharmonic,
}
