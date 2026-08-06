// /add — manual event entry. For shows foghorn's scrapers can't see: house
// concerts, one-off spaces, Instagram-only venues, a friend's gig you heard
// about in person. Server component fetches the venue list for the picker;
// the form itself is a client component.

import { notFound } from "next/navigation";
import { Suspense } from "react";

import AddEventForm from "../AddEventForm";
import { getJSON, type VenueOption } from "../lib/api";
import { getMe } from "../lib/serverAuth";

export default async function AddEventPage() {
  // Admin-only since multi-user (August 2026) — manual events are global
  // calendar rows. The backend enforces it; the 404 keeps the URL quiet.
  const me = await getMe();
  if (!me?.is_admin) notFound();

  const venues = await getJSON<VenueOption[]>("/api/venues");

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <header className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">Add an event</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          For shows the scrapers can&apos;t see — pick a tracked venue or type
          a new one.
        </p>
      </header>

      {venues === null ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Backend not reachable. Start it with{" "}
          <code className="font-mono">make backend-run</code>, then refresh.
        </div>
      ) : (
        <Suspense fallback={null}>
          <AddEventForm venues={venues} />
        </Suspense>
      )}
    </main>
  );
}
