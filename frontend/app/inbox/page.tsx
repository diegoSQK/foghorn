// /inbox — the mailing-list review queue (Phase 8). Emails land here (IMAP
// poll or the paste form); each card is an editable draft that approves into
// a manual event or gets rejected. Nothing enters the calendar unapproved.

import InboxCard from "./InboxCard";
import PasteEmailForm from "./PasteEmailForm";
import SendersManager from "./SendersManager";
import {
  getJSON,
  type MailSenderEntry,
  type PendingEventView,
  type VenueOption,
} from "../lib/api";

export default async function InboxPage() {
  const [pending, venues, senders] = await Promise.all([
    getJSON<PendingEventView[]>("/api/inbox"),
    getJSON<VenueOption[]>("/api/venues"),
    getJSON<MailSenderEntry[]>("/api/inbox/senders"),
  ]);

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <header className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">Inbox</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Mailing-list announcements awaiting review — edit the draft, then
          approve into the calendar or reject.
        </p>
      </header>

      {pending === null || venues === null ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Backend not reachable. Start it with{" "}
          <code className="font-mono">make backend-run</code>, then refresh.
        </div>
      ) : (
        <>
          <PasteEmailForm />

          {pending.length === 0 ? (
            <p className="mb-8 text-zinc-500 dark:text-zinc-400">
              The queue is empty. Emails arrive via{" "}
              <code className="font-mono">make mail-poll</code>, or paste one
              above.
            </p>
          ) : (
            <div className="mb-8 flex flex-col gap-4">
              {pending.map((row) => (
                <InboxCard key={row.id} row={row} venues={venues} />
              ))}
            </div>
          )}

          <SendersManager senders={senders ?? []} />
        </>
      )}
    </main>
  );
}
