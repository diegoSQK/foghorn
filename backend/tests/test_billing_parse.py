"""Billing-parser tests (#125).

The parser's bias is to under-split: a missed personnel list costs one
watchlist match, while a wrong split invents a performer that pollutes the
surname index — where a bogus name can block a correct resolution or become
the unique answer. So roughly half of these tests pin what it must *refuse*,
and every refusal case below is a real string from the live catalogue.
"""

from __future__ import annotations

import pytest

from foghorn.ingest.billing import parse_members


class TestTheShapesInTheTicket:
    def test_slash_separated_surnames(self) -> None:
        assert parse_members("Ochs/Johnston/Mezzacappa/Davis") == [
            "Ochs",
            "Johnston",
            "Mezzacappa",
            "Davis",
        ]

    def test_comma_list_with_trailing_project_name(self) -> None:
        assert parse_members(
            "Larry Ochs, Ben Davis, Darren Johnston, Lisa Mezzacappa "
            "- Subconscious Life"
        ) == ["Larry Ochs", "Ben Davis", "Darren Johnston", "Lisa Mezzacappa"]

    def test_parenthesised_personnel_with_instruments(self) -> None:
        assert parse_members(
            "Noise Witch(David Boyce-reeds&efxs, Brian Rodvien-drums, "
            "and Bryan Dean-bass)"
        ) == ["David Boyce", "Brian Rodvien", "Bryan Dean"]

    def test_roles_and_instruments_are_stripped(self) -> None:
        assert parse_members(
            "Vocalist Marina Crouse, with Danny Caron, guitar; "
            "and Ruth Davies, bass"
        ) == ["Marina Crouse", "Danny Caron", "Ruth Davies"]


class TestMustNotSplit:
    """Every string here is live catalogue data that a looser parser split."""

    @pytest.mark.parametrize(
        "billing",
        [
            # A slash inside a band name, not a personnel delimiter.
            "AC/DC",
            # A genre pairing either side of the slash.
            "Larry Vuckovich: Hector Lugo Jazz/Latin Trio feat. John Calloway",
            # Comma-separated band names — the single biggest false-positive
            # source, which is why a two-segment comma list needs annotation
            # evidence before it counts as personnel.
            "Earth, Wind & Fire",
            "Sincerely, Yours",
            "HEY, NOTHING – THE HOUND TOUR",
            "Dick Whittington, 90th Birthday",
            "Michael Wolff, solo",
            "Levitating the Pentagon, Nancy Kurshan",
            "Cabrillo Festival opening concert, 2026.",
            # "w/" is "with"; its slash is not a delimiter.
            "SONS OF CHAMPLIN W/ BILL CHAMPLIN",
            "Tom Reed w/ DJ E.T.",
            "MIKO MARKS RESIDENCY W/ SPECIAL GUEST KIAZI MALONGA",
            # Parenthesised text that isn't personnel.
            "SHELDON ALEXANDER FUNK JAM! (no cover charge)",
            "HONEY ISLAND SWAMP BAND (DIRECT from NEW ORLEANS)",
            # Mixed separators mean the structure isn't understood.
            "Erik Jekabson + Shulman/Shelby/Marrs",
            "Sixtyhurts 3: TION, Ava Khoohbor, Antimatter / Jacob Felix Heule",
            "String, Skin & Breath /Bristle",
            # An ordinary single act.
            "Lisa Mezzacappa Quintet",
            "The Rob Reich Swings Left Legacy Band Featuring Darren Johnston",
        ],
    )
    def test_refuses(self, billing: str) -> None:
        assert parse_members(billing) == []


class TestEdgeCases:
    def test_empty_and_blank(self) -> None:
        assert parse_members("") == []
        assert parse_members("   ") == []

    def test_trailing_separator_makes_no_empty_member(self) -> None:
        assert parse_members("Ochs/") == []
        assert "" not in parse_members("Ochs/Johnston/")

    def test_single_segment_is_not_a_list(self) -> None:
        assert parse_members("Mezzacappa") == []

    def test_placeholder_is_never_a_performer(self) -> None:
        assert "TBA" not in parse_members("MyVeronica/TBA")

    def test_alias_suffix_is_dropped(self) -> None:
        assert parse_members("Amendola/Frith/Dimuzio/Goldberg/Ochs aka Strolling Gnomes") == [
            "Amendola",
            "Frith",
            "Dimuzio",
            "Goldberg",
            "Ochs",
        ]

    def test_hyphenated_surname_survives(self) -> None:
        """The dash rule cuts instrument annotations, not real surnames."""
        members = parse_members(
            "Flavia Cervino-Wood, Derek Coombs, Harold Carr"
        )
        assert "Flavia Cervino-Wood" in members

    def test_duplicate_members_are_deduped(self) -> None:
        assert parse_members("Ochs/Johnston/Ochs") == ["Ochs", "Johnston"]

    def test_members_never_include_the_billing_itself(self) -> None:
        billing = "Kenny Warren, Liberty Ellman, Raffi Garabedian, Ben Goldberg"
        assert billing not in parse_members(billing)
