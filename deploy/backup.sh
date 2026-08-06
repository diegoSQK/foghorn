#!/bin/sh
# Nightly SQLite backup: a consistent .backup copy into the data volume's
# backups/ dir, keeping the most recent 14. Run from deploy/ via host cron:
#   0 3 * * * cd /opt/foghorn/deploy && ./backup.sh
# Copy the newest file off-box however you like (rsync/rclone) — a backup
# that lives only on the same disk is a snapshot, not a backup.
set -eu

docker compose exec -T backend python - <<'EOF'
import sqlite3, os, datetime, glob

os.makedirs("/data/backups", exist_ok=True)
stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
dest_path = f"/data/backups/foghorn-{stamp}.db"

src = sqlite3.connect("/data/foghorn.db")
dest = sqlite3.connect(dest_path)
with dest:
    src.backup(dest)
dest.close()
src.close()
print(f"backed up to {dest_path}")

backups = sorted(glob.glob("/data/backups/foghorn-*.db"))
for old in backups[:-14]:
    os.remove(old)
    print(f"pruned {old}")
EOF
