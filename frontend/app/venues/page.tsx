// /venues was folded into the main calendar as the ?venue_watchlist=true
// filter (UI consolidation, July 2026). This stub keeps old bookmarks and
// shared links working, carrying any other filter params across.

import { redirect } from "next/navigation";

export default async function VenuesRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(sp)) {
    const v = Array.isArray(value) ? value[0] : value;
    if (v !== undefined) query.set(key, v);
  }
  query.set("venue_watchlist", "true");
  redirect(`/?${query.toString()}`);
}
