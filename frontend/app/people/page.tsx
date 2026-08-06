// /people — admin-only user management (multi-user, August 2026). The
// backend enforces admin on every mutation; this page just 404s for
// everyone else so the URL leaks nothing.

import { notFound } from "next/navigation";

import PeopleManager from "./PeopleManager";
import { getJSON, type UserAdminView } from "../lib/api";
import { getMe, sessionHeaders } from "../lib/serverAuth";

export default async function PeoplePage() {
  const me = await getMe();
  if (!me?.is_admin) notFound();

  const headers = await sessionHeaders();
  const users = await getJSON<UserAdminView[]>("/api/auth/users", { headers });

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">People</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Who can use this foghorn — invite friends, manage their access.
        </p>
      </header>
      {users === null ? (
        <p className="text-zinc-500 dark:text-zinc-400">
          Couldn&apos;t load users — is the backend up?
        </p>
      ) : (
        <PeopleManager users={users} myId={me.id} />
      )}
    </main>
  );
}
