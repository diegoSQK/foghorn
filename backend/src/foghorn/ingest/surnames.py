"""Uniqueness-gated surname resolution.

The creative-music scene bills collectives by surname —
``Ochs/Johnston/Mezzacappa/Davis``. Once ``ingest.billing`` splits that into
four performers, three of them are bare surnames, and a bare surname can't
match a full-name watchlist follow: token-bag matching requires every token of
``lisa mezzacappa`` to appear in the performer name, and ``mezzacappa`` alone
doesn't carry ``lisa``.

**The tempting fix is wrong.** Relaxing the match rule so a performer name that
is a *subset* of the follow also counts would make a followed "Miles Davis"
match the bare ``Davis`` on this very bill, and on every other bill with a
Davis on it. A silent false positive in a digest is worse than a miss, because
it costs trust in every other row.

So instead of loosening matching, resolve the surname against the performers
foghorn already knows, and **gate the resolution on uniqueness**:

* exactly one known person's surname matches → link the show to that person
* two or more match (the ``Davis`` case) → leave the token bare, match nothing
* none match → leave it bare; never invent a person

Ambiguity stops being a judgement call and becomes a fact measurable from the
``performers`` table. The property gets *better* as the catalogue grows: a
surname that becomes ambiguous when a second bearer is ingested silently stops
resolving, which is the safe direction to fail.

**Who counts as "known" is the load-bearing detail.** The index is built only
from *person-shaped* names, because the raw table is full of billings that
merely end in a surname — "The Rob Reich Swings Left Legacy Band Featuring
Darren Johnston" is not a person called Johnston, and counting it would make
``johnston`` look ambiguous (blocking a correct resolution) or, worse, become
the unique answer for a surname nobody on the bill has.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from foghorn.models import Performer

# A person's name is two or three tokens: "Lisa Mezzacappa", "Ruth Brown
# Davies". Four-token names exist but four-token *billings* vastly outnumber
# them, so the cut stays here.
_MIN_PERSON_TOKENS = 2
_MAX_PERSON_TOKENS = 3

# Tokens that give a name away as a group, a programme, or a role rather than
# a person. A canonical name carrying one is never indexed as a person.
_NOT_A_PERSON = frozenset(
    """
    trio quartet quintet sextet septet octet nonet band orchestra ensemble
    group collective project allstars superband combo duo quartette
    jam session sessions night nights presents tribute revue residency
    featuring feat plays with and the of a an live free dj
    tour festival concert birthday anniversary release show party
    """.split()
)


@dataclass(frozen=True)
class SurnameIndex:
    """Known surnames → the single person who bears one, when unambiguous.

    Built once per ingest batch and read many times. ``ambiguous`` is kept
    rather than discarded so callers can log *why* a surname refused to
    resolve, which is the difference between a debuggable miss and a silent
    one.
    """

    unique: dict[str, Performer]
    ambiguous: frozenset[str]

    def resolve(self, token: str) -> Performer | None:
        """The person this bare surname denotes, or None when the catalogue
        can't say so unambiguously."""
        return self.unique.get(token)


def is_person_shaped(canonical_name: str) -> bool:
    """Whether a canonical performer name plausibly names one human.

    Conservative on purpose — a band wrongly admitted here can become the
    unique bearer of a surname and start attracting shows that aren't its.
    """
    tokens = canonical_name.split()
    if not (_MIN_PERSON_TOKENS <= len(tokens) <= _MAX_PERSON_TOKENS):
        return False
    if set(tokens) & _NOT_A_PERSON:
        return False
    # A token that's all digits ("5", "2026") means a band name or a date.
    return not any(token.isdigit() for token in tokens)


def build_index(conn: sqlite3.Connection) -> SurnameIndex:
    """Index every person-shaped performer by their last token."""
    by_surname: dict[str, list[Performer]] = {}
    for row in conn.execute(
        "SELECT id, display_name, canonical_name FROM performers"
    ):
        canonical = row[2] or ""
        if not is_person_shaped(canonical):
            continue
        surname = canonical.split()[-1]
        by_surname.setdefault(surname, []).append(
            Performer(id=row[0], display_name=row[1], canonical_name=canonical)
        )

    unique: dict[str, Performer] = {}
    ambiguous: set[str] = set()
    for surname, people in by_surname.items():
        # Two rows for the same person (the same canonical name ingested under
        # different display spellings) are one bearer, not an ambiguity.
        distinct = {person.canonical_name for person in people}
        if len(distinct) == 1:
            unique[surname] = people[0]
        else:
            ambiguous.add(surname)
    return SurnameIndex(unique=unique, ambiguous=frozenset(ambiguous))
