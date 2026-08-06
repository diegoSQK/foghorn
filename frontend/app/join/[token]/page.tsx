// /join/<token> — the invite-link landing page (multi-user, August 2026).
// The token in the URL is the account credential; JoinForm looks it up,
// claims/signs-in, and redirects home.

import JoinForm from "./JoinForm";

export default async function JoinPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <header className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">
          foghorn<span className="text-teal-600 dark:text-teal-400">.</span>
        </h1>
      </header>
      <JoinForm token={token} />
    </main>
  );
}
