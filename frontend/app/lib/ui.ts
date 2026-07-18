// Shared UI tokens. The accent is a foggy-harbor teal (it's called foghorn);
// change it here and every chip/link/button follows. Badge palettes stay
// per-meaning (emerald = local act, amber = jam, sky = added by you) so the
// accent never competes with semantic color.

/** Filter chip — filled with the accent when active. */
export function chipClass(active: boolean): string {
  return `rounded-full border px-3 py-1 text-sm transition-colors ${
    active
      ? "border-teal-700 bg-teal-700 text-white dark:border-teal-500 dark:bg-teal-500 dark:text-zinc-950"
      : "border-zinc-300 text-zinc-700 hover:border-teal-600 hover:text-teal-700 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-teal-400 dark:hover:text-teal-300"
  }`;
}

/** Disabled "(soon)" chip — dashed, non-interactive. */
export const disabledChipClass =
  "cursor-not-allowed rounded-full border border-dashed border-zinc-200 px-3 py-1 text-sm text-zinc-400 dark:border-zinc-800 dark:text-zinc-600";

export const inputClass =
  "rounded-md border border-zinc-300 bg-transparent px-2 py-1 text-sm text-zinc-900 focus:border-teal-600 focus:outline-none dark:border-zinc-700 dark:text-zinc-100 dark:focus:border-teal-400";

/** Inline text link in the accent color. */
export const linkClass =
  "text-teal-700 underline decoration-teal-700/40 underline-offset-2 hover:decoration-teal-700 dark:text-teal-400 dark:decoration-teal-400/40 dark:hover:decoration-teal-400";

/** Primary action button (accent-filled). */
export const buttonClass =
  "rounded-full border border-teal-700 bg-teal-700 px-4 py-1.5 text-sm text-white transition-colors hover:border-teal-800 hover:bg-teal-800 disabled:opacity-50 dark:border-teal-500 dark:bg-teal-500 dark:text-zinc-950 dark:hover:border-teal-400 dark:hover:bg-teal-400";

/** Left-accent border for a day-grid show block, hue-matched to the genre
 * badge palette below; unknown/untagged genres fall back to the accent teal. */
export function genreAccentClass(genre: string | null | undefined): string {
  const palette: Record<string, string> = {
    jazz: "border-indigo-400 dark:border-indigo-600",
    rock: "border-rose-400 dark:border-rose-600",
    funk: "border-orange-400 dark:border-orange-600",
    electronic: "border-violet-400 dark:border-violet-600",
  };
  return palette[genre ?? ""] ?? "border-teal-500 dark:border-teal-600";
}

/** Tiny tinted badge for a venue genre. Colors are fixed per genre value so
 * scanning a mixed list works; unknown genres fall back to neutral. */
export function genreBadgeClass(genre: string): string {
  const base =
    "rounded-full border px-1.5 py-px align-middle text-[10px] font-medium uppercase tracking-wide";
  // Filled tints so the colors register at badge size (a thin outline reads
  // as gray). Jazz — the primary use case — gets the strongest fill.
  const palette: Record<string, string> = {
    jazz: "border-indigo-400 bg-indigo-100 text-indigo-900 dark:border-indigo-700 dark:bg-indigo-950 dark:text-indigo-300",
    rock: "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-300",
    funk: "border-orange-300 bg-orange-50 text-orange-800 dark:border-orange-800 dark:bg-orange-950 dark:text-orange-300",
    electronic:
      "border-violet-300 bg-violet-50 text-violet-800 dark:border-violet-800 dark:bg-violet-950 dark:text-violet-300",
    eclectic:
      "border-zinc-300 text-zinc-600 dark:border-zinc-700 dark:text-zinc-400",
  };
  return `${base} ${palette[genre] ?? palette.eclectic}`;
}
