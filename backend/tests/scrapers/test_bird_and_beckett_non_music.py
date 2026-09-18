"""Non-music entries on Bird & Beckett's calendar (#124).

The shop's Google Calendar carries more than gigs: poetry readings, author
talks, and entries that aren't events at all ("closed for Thanksgiving",
"Glen Park Night Market"). The keyword heuristic missed those last two, and
they were ingested as shows.

**Tribe's categories are the better signal but cannot be the whole answer.**
The venue tags its own programming, which catches what a title never could —
"Amy O'Hair presents 'History Walks in Sunnyside'" reads like a gig. But the
two entries that prompted this ticket have *no Tribe event at all*, so absence
of a category must never be read as "not a show": that would drop the ~8% of
the calendar Tribe doesn't carry, real gigs included.

So a category decides when there is one, and the keyword list handles the
rest. These tests pin both halves and, most importantly, the case where they
disagree.
"""

from __future__ import annotations

import datetime as dt

import pytest

from foghorn.scrapers import bird_and_beckett as bb


def _details(*categories: str) -> bb.EventDetails:
    return bb.EventDetails(
        source_url="https://birdbeckett.com/event/x/",
        price_text=None,
        categories=frozenset(c.casefold() for c in categories),
    )


class TestCategoriesDecideWhenPresent:
    def test_live_music_is_a_show(self) -> None:
        assert not bb._is_non_music("Anything At All", _details("Live Music"))

    def test_a_jam_is_a_show(self) -> None:
        """A jam is programming foghorn wants; event_type tags it separately."""
        assert not bb._is_non_music(
            "Jam session hosted by the Vince Lateano Trio",
            _details("Happy Hour", "Jam Session", "Live Music"),
        )

    @pytest.mark.parametrize(
        "category", ["Poetry Reading", "Talks / Interviews", "Book Event"]
    )
    def test_non_music_categories_drop(self, category: str) -> None:
        assert bb._is_non_music("A Perfectly Gig-Like Title", _details(category))

    def test_a_category_beats_the_title(self) -> None:
        """The whole reason to prefer categories: this title has no keyword a
        heuristic could catch, and it's a walking tour."""
        title = "Amy O'Hair presents \"History Walks in Sunnyside\""
        assert not bb._is_non_music(title)  # title alone: looks like a gig
        assert bb._is_non_music(title, _details("Talks / Interviews"))

    def test_music_wins_over_a_co_tagged_non_music_category(self) -> None:
        assert not bb._is_non_music(
            "Somebody's Trio", _details("Live Music", "Book Event")
        )


class TestKeywordsHandleWhatTribeDoesntCarry:
    @pytest.mark.parametrize(
        "title",
        ["closed for Thanksgiving", "Closed for the holidays", "Glen Park Night Market"],
    )
    def test_the_reported_entries_drop_with_no_category(self, title: str) -> None:
        """These have no Tribe event, so categories can't help."""
        assert bb._is_non_music(title, None)

    def test_a_real_gig_with_no_category_is_kept(self) -> None:
        """The property that matters most: absence of a Tribe match must never
        mean "not a show". Will Bernard + Beth Custer is a real November date
        Tribe doesn't carry."""
        assert not bb._is_non_music("Will Bernard + Beth Custer", None)
        assert not bb._is_non_music("Will Bernard + Beth Custer", _details())

    def test_an_event_tribe_tagged_nothing_falls_back_to_the_title(self) -> None:
        assert bb._is_non_music("An Evening of Poetry", _details())
        assert not bb._is_non_music("Some Quartet", _details())

    @pytest.mark.parametrize(
        "title",
        [
            "The Closed Circuit Quartet",  # "closed" alone must not fire
            "Market Street Ramblers",  # "market" alone must not fire
        ],
    )
    def test_the_new_keywords_are_narrow(self, title: str) -> None:
        """"closed for" and "night market" are phrases precisely because the
        bare words are plausible inside a band name."""
        assert not bb._is_non_music(title, None)


class TestParsing:
    def test_categories_are_read_off_the_feed(self) -> None:
        index = bb.build_detail_index(
            [
                {
                    "url": "https://birdbeckett.com/event/x/",
                    "start_date": "2026-11-22 17:00:00",
                    "categories": [
                        {"name": "Live Music"},
                        {"name": "Jam Session"},
                    ],
                }
            ]
        )
        details = index[(dt.date(2026, 11, 22), dt.time(17, 0))]
        assert details.categories == {"live music", "jam session"}

    def test_an_event_with_no_categories_key(self) -> None:
        index = bb.build_detail_index(
            [
                {
                    "url": "https://birdbeckett.com/event/x/",
                    "start_date": "2026-11-22 17:00:00",
                }
            ]
        )
        assert index[(dt.date(2026, 11, 22), dt.time(17, 0))].categories == frozenset()

    def test_a_tribe_outage_does_not_change_which_titles_drop(self) -> None:
        """Fail-open, as #122 established: with no index, the filter is
        exactly the keyword heuristic and the show set is unchanged from
        before Tribe existed — plus the two non-events, which is the fix."""
        assert bb._is_non_music("closed for Thanksgiving", None)
        assert not bb._is_non_music("Ben Goldberg Trio", None)
