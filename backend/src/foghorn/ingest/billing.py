"""Split a multi-artist billing into the individual musicians it names.

Venues bill collectives in a handful of recognisable shapes, and foghorn's
creative-music wheelhouse leans hard on the ones that name people rather than
bands::

    Ochs/Johnston/Mezzacappa/Davis
    Larry Ochs, Ben Davis, Darren Johnston, Lisa Mezzacappa - Subconscious Life
    Noise Witch(David Boyce-reeds&efxs, Brian Rodvien-drums, and Bryan Dean-bass)
    Vocalist Marina Crouse, with Danny Caron, guitar; and Ruth Davies, bass

Until this module existed each of those was stored as a *single* performer, so
following "Lisa Mezzacappa" never matched the first one — the watchlist's
token-bag rule needs a `mezzacappa` performer to match against, and there
wasn't one.

**This never rewrites the billing.** Per ``AGENTS.md`` → Conventions the
display string is the venue's to choose; the members found here become
*additional* ``show_performers`` rows and the headliner keeps the whole billing
as its ``display_name``/``canonical_name``. That also keeps the dedupe natural
key ``(venue_id, start_local_date, start_local_time, headliner_canonical)``
untouched, so parsing an existing row doesn't churn its id or orphan its
``event_type_overrides`` rule.

**Bias: under-split.** A missed personnel list costs one watchlist match. A
wrong split invents a performer that pollutes the surname index in
``ingest.surnames``, where a bogus name can silently *block* a correct
resolution (two known "Davis"es refuse to resolve) or, worse, become the unique
answer. So every rule here refuses when it isn't confident — ``Jazz/Latin
Trio`` and ``AC/DC`` are both left alone, and the tests pin that.
"""

from __future__ import annotations

import re

# Words that mean "this segment is not a person's name". Instruments and their
# common abbreviations, plus the role nouns venues prefix to a name.
_INSTRUMENTS = frozenset(
    """
    guitar guitars gtr bass basses upright drums drum percussion perc
    piano keys keyboard keyboards organ b3 hammond rhodes synth synths
    sax saxophone saxes alto tenor soprano baritone bari reeds woodwinds
    trumpet cornet trombone tuba horn horns flute clarinet violin viola
    cello strings harp vibes vibraphone marimba accordion banjo mandolin
    fiddle harmonica turntables electronics efx efxs fx laptop
    vocals vocal voice vox singer vocalist drummer bassist guitarist
    pianist saxophonist trumpeter organist percussionist composer
    """.split()
)

# Connectives and framing words dropped from the *edges* of a member segment.
_CONNECTIVES = frozenset(
    "with and feat featuring plus special guest guests presents presenting".split()
)

# A segment carrying any of these is a band/programme name, not one musician.
# Used to veto a whole split, since one band-shaped segment usually means the
# separator wasn't a personnel delimiter at all.
_COLLECTIVE_MARKERS = frozenset(
    """
    trio quartet quintet sextet septet octet nonet band orchestra ensemble
    group collective project allstars all-stars superband combo duo
    jam session sessions night nights presents tribute revue
    residency tour festival concert birthday anniversary release solo
    """.split()
)

# Genre words that appear either side of a slash in a *style* pairing
# ("Jazz/Latin Trio", "Rock/Soul Revue") rather than a personnel list.
_GENRE_WORDS = frozenset(
    """
    jazz latin rock soul funk blues folk country pop hip hop rap indie punk
    metal electronic techno house disco reggae world classical gospel r
    americana bluegrass swing bebop fusion afrobeat salsa cumbia
    """.split()
)

# A bare surname shorter than this is too likely to be an initialism
# ("AC/DC", "CW/MC") to treat as a person.
_MIN_BARE_SURNAME_CHARS = 3

# Personnel segments rarely run long; a "member" of five words is a band name.
_MAX_MEMBER_TOKENS = 4


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _looks_like_collective(segment: str) -> bool:
    return bool(set(_words(segment)) & _COLLECTIVE_MARKERS)


def _strip_annotation(segment: str) -> str:
    """Drop an instrument annotation from one member segment.

    Venues attach the instrument with a dash (``David Boyce-reeds&efxs``), a
    comma (handled by the caller splitting on it), or parentheses
    (``Ruth Davies (bass)``).
    """
    segment = re.sub(r"\([^)]*\)", " ", segment)
    # "Name - instrument" / "Name-instrument": cut at the dash when what
    # follows is instrument vocabulary, so hyphenated surnames survive
    # ("Cervino-Wood" keeps its dash, "Boyce-reeds" loses it).
    parts = re.split(r"\s*[-–—]\s*", segment)
    if len(parts) > 1:
        kept = [parts[0]]
        for part in parts[1:]:
            words = _words(part)
            if words and all(word in _INSTRUMENTS for word in words):
                break
            kept.append(part)
        segment = "-".join(kept) if len(kept) > 1 else kept[0]
    return segment.strip(" \t.,;:&")


# Placeholders venues use for an unannounced act. Never a performer.
_PLACEHOLDERS = frozenset("tba tbd tbc".split())


def _clean_member(segment: str) -> str | None:
    """Normalize one candidate member to a display string, or None if it isn't
    a person's name."""
    # "Ochs aka Strolling Gnomes" — the alias belongs to the collective, and
    # the musician is the part before it.
    segment = re.split(r"\s+aka\s+", segment, flags=re.IGNORECASE)[0]
    segment = _strip_annotation(segment)
    tokens = segment.split()
    # Peel connectives and role nouns off both ends ("with Danny Caron",
    # "Vocalist Marina Crouse", "and Ruth Davies").
    while tokens and _words(tokens[0]) and _words(tokens[0])[0] in (
        _CONNECTIVES | _INSTRUMENTS
    ):
        tokens.pop(0)
    while tokens and _words(tokens[-1]) and _words(tokens[-1])[-1] in (
        _CONNECTIVES | _INSTRUMENTS
    ):
        tokens.pop()
    if not tokens:
        return None
    cleaned = " ".join(tokens).strip(" \t.,;:&")
    words = _words(cleaned)
    if not words or len(words) > _MAX_MEMBER_TOKENS:
        return None
    if all(word in _PLACEHOLDERS for word in words):
        return None
    # A pure instrument/connective segment ("guitar", "and") is annotation
    # left over from the split, not a member.
    if all(word in _INSTRUMENTS | _CONNECTIVES for word in words):
        return None
    if _looks_like_collective(cleaned):
        return None
    # A single bare token must look like a surname, not an initialism.
    if len(words) == 1 and len(words[0]) < _MIN_BARE_SURNAME_CHARS:
        return None
    return cleaned


# Characters that mean a segment has structure this parser doesn't model.
# Seeing one is a veto rather than a best effort: "Sixtyhurts 3: TION" and
# "DJ LOGIC & FRIENDS [LAZWELL" are not people, and guessing makes them so.
_COMMA_SEGMENT_VETO = re.compile(r"[/:\[\]]")
_SLASH_SEGMENT_VETO = re.compile(r"[&+,:(\[]")


def _split_members(
    body: str, pattern: str, *, allow_bare: bool
) -> tuple[list[str], bool]:
    """Split on a separator and clean each segment.

    Returns ``(members, saw_annotation)``. A segment that cleans to nothing
    *because it was pure annotation* ("guitar", "bass") is dropped and flagged
    — that's the signal that this really is a personnel list. A segment that
    fails for any other reason vetoes the whole split and returns ``([],
    False)``: a separator yielding one good name and one piece of junk was
    probably not a personnel delimiter, and half-parsing it invents a
    performer.

    ``allow_bare`` permits single-token members (the ``Ochs/Johnston`` shape).
    Comma lists require two tokens per member, because one-token comma
    segments are overwhelmingly band names ("Earth, Wind & Fire").
    """
    raw = [seg for seg in re.split(pattern, body) if seg.strip()]
    if len(raw) < 2:
        return [], False
    members: list[str] = []
    saw_annotation = False
    for segment in raw:
        if _is_pure_annotation(segment):
            saw_annotation = True
            continue
        member = _clean_member(segment)
        if member is None:
            return [], False
        if not allow_bare and len(_words(member)) < 2:
            return [], False
        if _words(segment) != _words(member):
            # Something was stripped (a role word, an instrument) — evidence
            # that this is personnel rather than a list of act names.
            saw_annotation = True
        members.append(member)
    return members, saw_annotation


def _is_pure_annotation(segment: str) -> bool:
    words = _words(segment)
    return bool(words) and all(
        word in _INSTRUMENTS | _CONNECTIVES for word in words
    )


def _parse_slash(billing: str) -> list[str]:
    """``Ochs/Johnston/Mezzacappa/Davis`` → four surnames.

    Refuses a genre pairing (``Jazz/Latin Trio``), an initialism (``AC/DC``),
    and the ``w/`` abbreviation for "with" — all three are common enough in
    the catalogue to be worth an explicit veto, and all three would otherwise
    mint performers that never existed.
    """
    if "/" not in billing:
        return []
    segments = [seg for seg in billing.split("/") if seg.strip()]
    if len(segments) < 2:
        return []
    for segment in segments:
        if _SLASH_SEGMENT_VETO.search(segment):
            return []
        words = _words(segment)
        if not words:
            return []
        # A style pairing has a genre word directly adjacent to the slash.
        if words[-1] in _GENRE_WORDS or words[0] in _GENRE_WORDS:
            return []
        # "SONS OF CHAMPLIN W/ BILL CHAMPLIN" — the slash belongs to "w/".
        if words[-1] == "w":
            return []
    members, _ = _split_members(billing, r"/", allow_bare=True)
    return members


def _parse_parenthesised(billing: str) -> tuple[str | None, list[str]]:
    """``Noise Witch(David Boyce-reeds, ...)`` → ("Noise Witch", [members]).

    Only fires when the parenthesised body reads as a personnel list: at least
    two comma-separated segments that all clean to two-token names. That keeps
    ``(no cover charge)`` and ``(DIRECT from NEW ORLEANS)`` out.
    """
    match = re.search(r"\(([^)]*)\)", billing)
    if match is None:
        return None, []
    members, _ = _split_members(match.group(1), r",", allow_bare=False)
    if len(members) < 2:
        return None, []
    lead = billing[: match.start()].strip(" \t.,;:&-")
    return (lead or None), members


def _parse_delimited(billing: str) -> list[str]:
    """Comma/semicolon personnel lists, with or without role and instrument
    annotations. A trailing project name after a dash or colon
    (``... - Subconscious Life``) is dropped before splitting.

    Deliberately strict, because comma-separated band names are everywhere.
    A split needs **three** members, or two plus annotation evidence — so
    ``Kenny Warren, Liberty Ellman, Raffi Garabedian`` parses and
    ``Dick Whittington, 90th Birthday`` does not.
    """
    body = re.split(r"\s+[-–—:]\s+", billing)[0]
    if not re.search(r"[,;]", body):
        return []
    if _COMMA_SEGMENT_VETO.search(body):
        return []
    members, saw_annotation = _split_members(body, r"[,;]", allow_bare=False)
    if len(members) >= 3 or (len(members) >= 2 and saw_annotation):
        return members
    return []


def parse_members(billing: str) -> list[str]:
    """Musicians named inside a billing, in billing order.

    Returns ``[]`` when the billing names one act (the common case) or when no
    rule is confident enough to split. Never includes the billing itself.
    """
    if not billing or not billing.strip():
        return []

    lead, members = _parse_parenthesised(billing)
    if members:
        # The lead is the group name and already the headliner; the members are
        # the addition. Include the lead only when it's itself person-shaped
        # (a duo billed "Name (a, b)" is rare but harmless to keep).
        return _dedupe(members)

    for parser in (_parse_slash, _parse_delimited):
        members = parser(billing)
        if len(members) >= 2:
            return _dedupe(members)
    return []


def _dedupe(members: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for member in members:
        key = " ".join(_words(member))
        if key and key not in seen:
            seen.add(key)
            out.append(member)
    return out
