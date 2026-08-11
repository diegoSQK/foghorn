// Multi-select facet params.
//
// Every facet chip group (region, neighborhood, genre, origin, type) stores its
// selection as one comma-separated URL param. Within a facet the values OR
// together; across facets they AND — the standard faceted-search shape. A
// single value is just the one-element case, so old single-value URLs and
// bookmarks keep working untouched.
//
// Time-of-day stays single-select on purpose: "early" and "late" are exact
// complements, so selecting both is identical to selecting neither.

/** Parse a comma-separated facet param into trimmed, de-duplicated values. */
export function facetValues(param: string | null): string[] {
  if (!param) return [];
  return [
    ...new Set(
      param
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean),
    ),
  ];
}

/**
 * Add or remove one value, returning the new param string — or `null` when the
 * selection empties, so the caller deletes the param rather than leaving
 * `?genre=` behind.
 */
export function toggleFacet(param: string | null, value: string): string | null {
  const current = facetValues(param);
  const next = current.includes(value)
    ? current.filter((v) => v !== value)
    : [...current, value];
  return next.length ? next.join(",") : null;
}

/** Whether `value` is currently selected in a facet param. */
export function facetHas(param: string | null, value: string): boolean {
  return facetValues(param).includes(value);
}
