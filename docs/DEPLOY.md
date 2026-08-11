# Deploying foghorn to a VPS

How to run foghorn publicly for friends: one small Linux box, Docker Compose,
Caddy for automatic HTTPS, SQLite on a volume. The artifacts live in
[`deploy/`](../deploy); this doc is the runbook. (The Tailscale fleet
deployment on the laptop is unaffected — this is a second, public instance.)

## What you need

- A VPS with **2GB+ RAM** (the Next.js build is the constraint; Hetzner CX22
  or a DigitalOcean basic droplet are both fine) running a current Debian or
  Ubuntu.
- A domain (or subdomain) with an **A record pointed at the box** *before*
  first start — Caddy needs it resolving to issue the Let's Encrypt cert.

## First-time setup

On the box:

```bash
# 1. Docker (official convenience script, installs compose v2)
curl -fsSL https://get.docker.com | sh

# 2. Get the repo
sudo mkdir -p /opt/foghorn && sudo chown "$USER" /opt/foghorn
git clone https://github.com/diegoSQK/foghorn.git /opt/foghorn
cd /opt/foghorn/deploy

# 3. Configure the domain
cp .env.example .env
$EDITOR .env          # FOGHORN_DOMAIN=shows.example.com

# 4. Build and start (first build takes a few minutes)
docker compose up -d --build
```

Then create your admin account and get your login link:

```bash
docker compose exec backend python -m foghorn.cli.auth bootstrap
# → login link: /join/<token>   — open https://<your-domain>/join/<token>
```

Invite friends from the **People** page in the app (admin-only), or from the
CLI: `docker compose exec backend python -m foghorn.cli.auth invite "Ada"`.

### Bringing your existing data

To start the public instance from the laptop's database instead of empty:

```bash
# on the laptop
scp ~/fleet-data/foghorn/foghorn.db you@box:/tmp/foghorn.db
# on the box
docker compose stop backend
docker compose cp /tmp/foghorn.db backend:/data/foghorn.db   # or: docker run --rm -v deploy_foghorn-data:/data -v /tmp:/tmp alpine cp /tmp/foghorn.db /data/
docker compose start backend
```

On first connection the schema migration re-keys the watchlists to a
bootstrap admin — run `auth bootstrap` after, and that admin owns the
existing watchlist/pins (that's you).

## Continuous deploy

Merges to `main` auto-deploy via [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)
once three repo secrets exist (Settings → Secrets and variables → Actions):

- `DEPLOY_HOST` — the box's hostname or IP
- `DEPLOY_USER` — the SSH user (must be able to run docker; add to the
  `docker` group)
- `DEPLOY_SSH_KEY` — a dedicated private key (`ssh-keygen -t ed25519`),
  public half in the box's `~/.ssh/authorized_keys`

Until the secrets are set the workflow no-ops, so it's safe to merge this
before the box exists. The deploy is `git checkout origin/main` +
`docker compose up -d --build` — idempotent, and manual runs work via the
workflow_dispatch button.

## Backups

```bash
# host crontab (crontab -e):
0 3 * * * cd /opt/foghorn/deploy && ./backup.sh >> /var/log/foghorn-backup.log 2>&1
```

`backup.sh` takes a consistent SQLite `.backup` into the data volume
(`backups/`, most recent 14 kept). Ship the newest one off-box periodically
(rsync/rclone to the laptop or object storage) — same-disk copies don't
survive a dead disk.

## Things to know

- **Scraper IPs.** The nightly scrape now runs from a datacenter IP. Most of
  the ~70 sources won't care; the WAF-touchy ones (Wix 429s, The Big Easy's
  IP-keyed blocks) may get stricter. If a venue that works from the laptop
  fails from the box, the fallback is hybrid: keep scraping on the laptop
  and ship the DB over (reverse of "Bringing your existing data"), or run
  that one scraper locally on a cron.
- **macOS-only OCR.** Apple Vision doesn't exist on Linux; the image
  installs the `rapidocr` extra so the flyer venues (Little Hill Lounge,
  Poor House Bistro) keep working, at slightly lower OCR quality.
- **JamBase / SFJAZZ flag.** `FOGHORN_SFJAZZ_ENABLED` stays `0` in
  production (pinned in compose): the JamBase POC runs under personal-eval
  terms that don't cover public display.
- **Secure cookies.** `FOGHORN_SECURE_COOKIES=1` is set in compose — session
  cookies are HTTPS-only in production. Don't set it for the Tailscale
  fleet deployment, which serves plain HTTP.
- **Single-user mode.** `FOGHORN_SINGLE_USER` **must stay `0`** on the VPS
  (pinned in compose): it resolves every unauthenticated request as the
  bootstrap admin, which on a public deployment hands admin to the internet.
  It exists for the Tailscale fleet deployment only.
- **Mail ingest.** `make mail-poll` (Phase 8) isn't wired into the container
  scheduler; if you want it on the box, add a host cron running
  `docker compose exec -T backend python -m foghorn.cli.mail_poll` with the
  `FOGHORN_IMAP_*` env vars in `deploy/.env` and passed through in compose.
