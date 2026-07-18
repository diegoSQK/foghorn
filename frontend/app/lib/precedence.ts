// Display precedence for "followed" shows: anything at a watched venue or
// with a watchlist-matched performer floats to the top of date groups (and
// its venue column to the left of the day grid). Matching mirrors the
// backend's token-bag semantics (repo/performer_match.py): every token of a
// watchlist entry must appear as a whole token of the performer's canonical
// name — so a "lisa mezzacappa" follow floats any billing she's inside.

import type { ShowView } from "./api";

function matchesTokenBag(entryCanonical: string, performerCanonical: string): boolean {
  const performerTokens = new Set(performerCanonical.split(" "));
  const entryTokens = entryCanonical.split(" ").filter(Boolean);
  return (
    entryTokens.length > 0 &&
    entryTokens.every((token) => performerTokens.has(token))
  );
}

function performerFollowed(canonical: string, watchlistCanon: Set<string>): boolean {
  for (const entry of watchlistCanon) {
    if (matchesTokenBag(entry, canonical)) return true;
  }
  return false;
}

/** Ids of shows that deserve precedence: at a watched venue, or with any
 * performer (headliner or support) matching any watchlist entry. */
export function followedShowIds(
  shows: ShowView[],
  watchlistCanon: Set<string>,
  watchedVenueSlugs: Set<string>,
): Set<number> {
  const ids = new Set<number>();
  for (const show of shows) {
    if (
      watchedVenueSlugs.has(show.venue.slug) ||
      performerFollowed(show.headliner.canonical, watchlistCanon) ||
      show.support.some((p) => performerFollowed(p.canonical, watchlistCanon))
    ) {
      ids.add(show.id);
    }
  }
  return ids;
}

/** Stable followed-first ordering; within each bucket the incoming (time)
 * order is preserved. */
export function sortFollowedFirst(
  shows: ShowView[],
  followedIds: Set<number>,
): ShowView[] {
  return [
    ...shows.filter((show) => followedIds.has(show.id)),
    ...shows.filter((show) => !followedIds.has(show.id)),
  ];
}
