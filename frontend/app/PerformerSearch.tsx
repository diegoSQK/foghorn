"use client";

// Free-text performer search (Phase 3.3). Its own component so composing it into
// FilterBar is a one-line change (keeps the merge surface with #21 tiny). Like
// the rest of the filter framework, the URL is the source of truth: typing
// debounces a `?performer_query=` push (~300ms), and the value re-seeds from the
// URL on external changes (Clear filters, back/forward, shared links).

import { useEffect, useRef, useState } from "react";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

const DEBOUNCE_MS = 300;

export default function PerformerSearch() {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname(); // keep search on the current route (/ or /watchlist)
  const urlQuery = params.get("performer_query") ?? "";

  const [value, setValue] = useState(urlQuery);
  // Tracks the value reflected in the URL, so we can tell our own pushes apart
  // from external URL changes without clobbering mid-type input.
  const synced = useRef(urlQuery);

  // Debounce: push to the URL after the user pauses typing.
  useEffect(() => {
    if (value === synced.current) return;
    const timer = setTimeout(() => {
      synced.current = value;
      const next = new URLSearchParams(params.toString());
      if (value.trim()) next.set("performer_query", value.trim());
      else next.delete("performer_query");
      const query = next.toString();
      router.push(query ? `${pathname}?${query}` : pathname);
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [value, params, router, pathname]);

  // Resync the input when the URL changes from outside (Clear filters, back).
  useEffect(() => {
    if (urlQuery !== synced.current) {
      synced.current = urlQuery;
      setValue(urlQuery);
    }
  }, [urlQuery]);

  return (
    <div className="relative">
      {/* type="text" (not "search") on purpose: WebKit draws its own clear ×
          on search inputs next to ours, and the CSS to hide it gets stripped
          by the build's minifier. The explicit role keeps the a11y contract. */}
      <input
        type="text"
        role="searchbox"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Search performers…"
        aria-label="Search performers"
        className="w-full rounded-md border border-zinc-300 bg-transparent px-3 py-2 pr-9 text-sm text-zinc-900 placeholder:text-zinc-400 dark:border-zinc-700 dark:text-zinc-100"
      />
      {value && (
        <button
          type="button"
          onClick={() => setValue("")}
          aria-label="Clear search"
          className="absolute inset-y-0 right-2 my-auto h-5 w-5 rounded-full text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700 dark:hover:bg-zinc-700 dark:hover:text-zinc-200"
        >
          ×
        </button>
      )}
    </div>
  );
}
