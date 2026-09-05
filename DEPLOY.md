# Running it in the office

Both containers run on the firm's own server. Staff open it from any machine on
the network. Nothing leaves the building.

```
office PC ──http──> server:80 ──> web (nginx)  ──> api (FastAPI)
                                                      │
                                                   ./data
                                        database + every uploaded document
```

---

## First install

On the server, once:

```bash
git clone https://github.com/jilsnshah/gst-compliance-portal.git /opt/nhs_sol
cd /opt/nhs_sol
cp .env.example .env
```

Edit `.env`:

```bash
SECRET_KEY=          # python3 -c "import secrets; print(secrets.token_urlsafe(48))"
ADMIN_EMAIL=partner@yourfirm.local
ADMIN_PASSWORD=      # you will change it after the first login
WEB_PORT=80
SEED_DEMO=false      # true would create admin@test.com / test123
```

Then:

```bash
docker compose up -d --build
```

That migrates the database, creates the one administrator, and starts both
containers. Staff go to `http://<server-ip>/`.

Find the server's address with `hostname -I`. Give it a fixed IP or a DNS name
on the office network so the URL never changes.

---

## Day one

1. Sign in as the administrator.
2. **Team activity → Add employee** for each person: name, email, password.
   Tell them their password; they can be changed later from the same page.
3. **Clients & files → Add a client** as each month's work comes up. A client is
   a name, phone, email and password; a file is one GSTIN. Clients do not need
   to log in during Stage 1 — staff upload on their behalf, and the portal
   records that they did.
4. Open a month on a file and work through it.

---

## Keeping it running

**Updates.** New version, no data loss:

```bash
cd /opt/nhs_sol && git pull && docker compose up -d --build
```

Migrations run automatically on start. This is why the schema is managed by
Alembic -- a model change no longer means rebuilding the database.

**Backups.** `./data` is the firm's entire record and there is only one copy.

```bash
./backup.sh                 # -> ./backups/nhs-YYYY-MM-DD-HHMM.tar.gz
./backup.sh /mnt/nas/gst    # or straight onto the NAS
```

Nightly, in the server's crontab (`crontab -e`):

```
15 21 * * *  cd /opt/nhs_sol && ./backup.sh /mnt/nas/gst >> /opt/nhs_sol/backups/backup.log 2>&1
```

Send it somewhere off this machine. A backup on the same disk does not survive
the disk failing.

**Restoring** replaces everything in `./data` and asks for confirmation:

```bash
./restore.sh backups/nhs-2026-08-12-2115.tar.gz
```

Test one restore into a spare copy before you ever need it for real.

**After a server reboot** the containers come back on their own
(`restart: unless-stopped`), as long as Docker itself starts at boot:
`sudo systemctl enable docker`.

**Checking on it:**

```bash
docker compose ps            # both should be Up
docker compose logs -f api   # what the API is doing
```

---

## Starting a second machine with the client list already in it

`bootstrap/gst_platform.db` is a committed snapshot of the database: every
client, file and login, no uploaded documents. It exists so a new machine does
not have to re-import the client sheet.

It is **not** the live database and `git pull` never touches `./data/`. Copy it
into place once, on a machine that has never been started:

```bash
mkdir -p data && cp bootstrap/gst_platform.db data/gst_platform.db
docker compose up -d --build
```

Never copy it over a `data/` that has been worked in -- it would replace real
work with a snapshot. To refresh the snapshot from the machine that holds the
record:

```bash
docker compose exec -T api python -c "
import sqlite3
src = sqlite3.connect('/data/gst_platform.db'); dst = sqlite3.connect('/data/.snapshot.db')
src.backup(dst); dst.close()"
docker compose cp api:/data/.snapshot.db bootstrap/gst_platform.db
docker compose exec -T api rm -f /data/.snapshot.db
```

Uploaded documents are not in it, and should not be -- they belong in backups
(`backup.sh`), not in git.

---

## Letting the office reach it over the network

The `web` container publishes `WEB_PORT` on every interface, so any machine on
the same network opens:

```
http://<this machine's IP>:<WEB_PORT>/
```

Find the address with `ipconfig getifaddr en0` on macOS, `hostname -I` on
Linux. The frontend talks to the API on the same origin through nginx, so there
is nothing else to configure -- no CORS entry, no API URL.

On macOS the firewall may ask to allow incoming connections the first time.
Give the machine a fixed IP (or a DHCP reservation) so the URL stops changing.

This is plain HTTP on the LAN. Do not forward the port to the internet without
TLS in front of it.

---

## Known limits for this stage

- Plain HTTP on the LAN. Fine inside the office; do not expose port 80 to the
  internet without putting TLS in front of it.
- SQLite, one writer at a time. Comfortable for ~20 staff; heavy simultaneous
  uploads will queue rather than fail.
- Notifications are in-app only. Nobody is emailed, so clients will not know to
  log in -- which is why staff upload on their behalf in Stage 1.
- No password reset. An administrator sets passwords from the team page.
- Uploads are checked by content and capped at 10 MB, but not virus-scanned.
