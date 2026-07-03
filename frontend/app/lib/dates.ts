// Pure date helpers shared by the server page and the client FilterBar.
// All dates are local-tz "YYYY-MM-DD" strings (the venue calendar is PT and so
// is the single user, so local-date math is the right granularity here).

function isoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function todayISO(): string {
  return isoDate(new Date());
}

export function addDaysISO(iso: string, days: number): string {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  date.setDate(date.getDate() + days);
  return isoDate(date);
}

// Friday–Sunday of the current weekend if it's already Fri/Sat/Sun, else the
// upcoming one.
export function thisWeekend(): { from: string; to: string } {
  const now = new Date();
  const dow = now.getDay(); // 0 = Sun, 6 = Sat
  const toFriday = dow === 0 ? -2 : dow === 6 ? -1 : 5 - dow;
  const friday = addDaysISO(isoDate(now), toFriday);
  return { from: friday, to: addDaysISO(friday, 2) };
}

// Monday of the week containing `iso` (weeks run Mon–Sun).
export function mondayOfISO(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  const dow = date.getDay(); // 0 = Sun
  return addDaysISO(iso, dow === 0 ? -6 : 1 - dow);
}

// First and last day of the month containing `iso`.
export function monthBoundsISO(iso: string): { from: string; to: string } {
  const [year, month] = iso.split("-").map(Number);
  const last = new Date(year, month, 0).getDate();
  const mm = String(month).padStart(2, "0");
  return {
    from: `${iso.slice(0, 4)}-${mm}-01`,
    to: `${iso.slice(0, 4)}-${mm}-${String(last).padStart(2, "0")}`,
  };
}

export function isISODate(value: string | undefined): value is string {
  return value !== undefined && /^\d{4}-\d{2}-\d{2}$/.test(value);
}
