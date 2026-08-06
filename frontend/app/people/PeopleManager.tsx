"use client";

// Admin user management (multi-user, August 2026): create invites, copy
// links, regenerate a lost/leaked link, disable accounts. Mutations refresh
// the server-rendered list.

import { useRouter } from "next/navigation";
import { useState } from "react";

import { API_BASE, type UserAdminView } from "../lib/api";
import { inputClass } from "../lib/ui";

export default function PeopleManager({
  users,
  myId,
}: {
  users: UserAdminView[];
  myId: number;
}) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState<number | null>(null);

  async function createInvite() {
    const displayName = name.trim();
    if (!displayName || busy) return;
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: displayName }),
      });
      if (res.ok) {
        setName("");
        router.refresh();
      }
    } finally {
      setBusy(false);
    }
  }

  async function copyLink(user: UserAdminView) {
    const url = `${window.location.origin}${user.invite_path}`;
    await navigator.clipboard.writeText(url);
    setCopied(user.id);
    setTimeout(() => setCopied((c) => (c === user.id ? null : c)), 1500);
  }

  async function regenerate(user: UserAdminView) {
    if (busy) return;
    if (
      !window.confirm(
        `Make a new link for ${user.display_name}? Their old link stops working (open sessions stay signed in).`,
      )
    )
      return;
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/auth/users/${user.id}/regenerate`, {
        method: "POST",
      });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  async function setDisabled(user: UserAdminView, disabled: boolean) {
    if (busy) return;
    if (
      disabled &&
      !window.confirm(
        `Disable ${user.display_name}? They're signed out everywhere and their link stops working (their watchlist is kept).`,
      )
    )
      return;
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/auth/users/${user.id}/disabled`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ disabled }),
      });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void createInvite();
        }}
      >
        <input
          className={`${inputClass} flex-1`}
          placeholder="Friend's name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button
          type="submit"
          disabled={busy || !name.trim()}
          className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-teal-800 disabled:opacity-50 dark:bg-teal-600 dark:hover:bg-teal-500"
        >
          Create invite
        </button>
      </form>

      <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
        {users.map((user) => (
          <li key={user.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-3">
            <span className={`font-medium ${user.disabled ? "text-zinc-400 line-through dark:text-zinc-600" : ""}`}>
              {user.display_name}
            </span>
            {user.is_admin && (
              <span className="rounded-full border border-teal-300 px-1.5 py-px text-[10px] font-medium uppercase tracking-wide text-teal-700 dark:border-teal-800 dark:text-teal-400">
                admin
              </span>
            )}
            {user.claimed_at === null && !user.disabled && (
              <span className="rounded-full border border-zinc-300 px-1.5 py-px text-[10px] font-medium uppercase tracking-wide text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
                invited
              </span>
            )}
            {user.email && (
              <span className="text-sm text-zinc-500 dark:text-zinc-400">{user.email}</span>
            )}
            <span className="ml-auto flex gap-3 text-sm">
              {!user.disabled && (
                <>
                  <button
                    type="button"
                    onClick={() => copyLink(user)}
                    className="text-teal-700 hover:underline dark:text-teal-400"
                  >
                    {copied === user.id ? "Copied!" : "Copy link"}
                  </button>
                  <button
                    type="button"
                    onClick={() => regenerate(user)}
                    className="text-zinc-500 hover:underline dark:text-zinc-400"
                  >
                    New link
                  </button>
                </>
              )}
              {user.id !== myId &&
                (user.disabled ? (
                  <button
                    type="button"
                    onClick={() => setDisabled(user, false)}
                    className="text-zinc-500 hover:underline dark:text-zinc-400"
                  >
                    Re-enable
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => setDisabled(user, true)}
                    className="text-amber-700 hover:underline dark:text-amber-400"
                  >
                    Disable
                  </button>
                ))}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        Send someone their link however you like (text, email) — opening it
        creates their account, and the same link signs them back in on any
        device. &ldquo;New link&rdquo; if one leaks or gets lost.
      </p>
    </div>
  );
}
