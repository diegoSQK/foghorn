"""Token-bag performer matching (Phase 4.1) — the canonical performer-match
utility shared by free-text search (3.3) and the watchlist (4.1).

A query matches a performer iff **every whitespace token** of the query's
canonical form appears as a **whole token** in the performer's canonical form.
Both sides are canonicalized first (by ``ingest.pipeline.canonicalize`` —
lowercased, accent-stripped, punctuation-removed, single-spaced), so "Joshua
Redman" and "Redman, Joshua" both reduce to the token set ``{joshua, redman}``
and match "joshua redman quartet". Whole-token, not character-substring, is the
point: "redm" does *not* match "redman" (that precision is why the watchlist
wants this over 3.3's old substring match).

Future fuzzy escalation (FTS5 + trigram for typo tolerance) is deferred — see
``docs/PROJECT_PLAN.md`` Phase 4 / Phase 7.
"""

from __future__ import annotations


def matches_token_bag(query_canonical: str, target_canonical: str) -> bool:
    """True iff every token of ``query_canonical`` is a whole token of
    ``target_canonical``. Empty query → ``False`` (callers treat an empty query
    as 'no filter' and don't call this)."""
    query_tokens = query_canonical.split()
    if not query_tokens:
        return False
    target_tokens = set(target_canonical.split())
    return all(token in target_tokens for token in query_tokens)


def token_match_sql(
    column: str, token_bags: list[list[str]], prefix: bool = False
) -> tuple[str, list[str]]:
    """Build a parameterized SQL predicate that is true when ``column``'s
    canonical name token-matches **any** of ``token_bags`` (AND within a
    bag, OR across bags).

    Implemented by padding the column with spaces and matching ``'% token %'``
    per token, so only whole space-delimited tokens match. With
    ``prefix=True`` the trailing space is dropped (``'% token%'``) so each
    query token matches as a *token prefix* — "mezz" matches "mezzacappa" —
    which is what a search-as-you-type box needs; watchlist matching stays
    whole-token for precision. Tokens are already canonicalized to
    ``[a-z0-9 ]`` upstream, so they carry no SQL ``LIKE`` wildcards
    (``%`` / ``_``) and need no escaping; ``column`` is a code-supplied
    identifier, never user input. Returns ``("", [])`` when there's nothing to
    match (caller skips the clause).
    """
    wrapped = f"(' ' || {column} || ' ')"
    pattern = "% {token}%" if prefix else "% {token} %"
    or_clauses: list[str] = []
    params: list[str] = []
    for tokens in token_bags:
        and_clauses = [f"{wrapped} LIKE ?" for _ in tokens]
        if and_clauses:
            params.extend(pattern.format(token=token) for token in tokens)
            or_clauses.append("(" + " AND ".join(and_clauses) + ")")
    if not or_clauses:
        return "", []
    return "(" + " OR ".join(or_clauses) + ")", params
