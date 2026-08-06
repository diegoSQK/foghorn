"""User administration from the command line (multi-user, August 2026).

Runs against the DB at ``FOGHORN_DB_PATH`` — the Makefile targets set it to
the live path, same as the other DB-writing targets.

- ``bootstrap``: ensure an admin account exists and print its login link.
  This is how the very first user (the operator) gets in; safe to re-run.
- ``invite <name>``: create a friend's account and print their invite link.
- ``list``: show every account with claim/disabled state.

Links are printed as paths — prefix with wherever the frontend is served
(e.g. ``https://your-domain`` or ``http://laptop:3100``).
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from foghorn.repo import db
from foghorn.repo import users as users_repo


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m foghorn.cli.auth")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap", help="ensure an admin exists; print its login link")
    invite = sub.add_parser("invite", help="create a user; print their invite link")
    invite.add_argument("display_name")
    invite.add_argument("--admin", action="store_true")
    sub.add_parser("list", help="list all accounts")
    args = parser.parse_args()

    conn = db.connect()
    try:
        if args.command == "bootstrap":
            admin = next((u for u in users_repo.list_all(conn) if u.is_admin), None)
            if admin is None:
                admin = users_repo.create_invite(conn, "Admin", is_admin=True)
                # The operator's own account: no separate claim step needed.
                conn.execute(
                    "UPDATE users SET claimed_at = ? WHERE id = ?",
                    (datetime.now(UTC).isoformat(), admin.id),
                )
                conn.commit()
                print(f"created admin account (id {admin.id})")
            else:
                print(f"admin account exists: {admin.display_name} (id {admin.id})")
            print(f"login link: /join/{admin.invite_token}")
        elif args.command == "invite":
            user = users_repo.create_invite(
                conn, args.display_name, is_admin=args.admin
            )
            print(f"created {user.display_name} (id {user.id})")
            print(f"invite link: /join/{user.invite_token}")
        elif args.command == "list":
            for user in users_repo.list_all(conn):
                flags = "".join(
                    [
                        " admin" if user.is_admin else "",
                        " disabled" if user.disabled else "",
                        " unclaimed" if user.claimed_at is None else "",
                    ]
                )
                print(f"{user.id}\t{user.display_name}{flags}\t/join/{user.invite_token}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
