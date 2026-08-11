# Running the demo

Backend in Docker on your laptop, frontend wherever you like. All data — the
SQLite database and every uploaded document — stays in `./data` on your machine.

---

## Read this first: Vercel cannot reach your laptop

A frontend on Vercel runs in the **visitor's** browser. When that page calls
`http://localhost:8010`, "localhost" means *the visitor's own machine*, not yours.

- **You** open the Vercel URL on your laptop → works, because your laptop is
  running the backend.
- **Anyone else** opens it → the app loads and every request fails. There is no
  route from their browser to your laptop.

So pick based on who is watching:

| Who sees the demo | Use |
|---|---|
| Just you, on your laptop | **Option A** — everything local |
| Someone else, anywhere | **Option B** — tunnel + Vercel |

---

## Option A — everything on your laptop

```bash
docker compose up -d --build     # API on http://localhost:8010
cd frontend && npm run dev       # UI  on http://localhost:5173
```

Sign in with `admin@test.com` / `test123`. Nothing else to configure.

---

## Option B — Vercel frontend, backend still on your laptop

A tunnel gives your laptop a public HTTPS address. The backend never leaves your
machine; the tunnel just forwards requests to it.

**1. Start the backend and a tunnel**

```bash
docker compose up -d --build
docker compose logs --tail 60 tunnel | grep -B4 "Registered tunnel connection"
#  -> https://random-words-1234.trycloudflare.com
```

Read the URL from the newest `Registered tunnel connection`, not with a plain
`grep trycloudflare`: the logs accumulate across restarts, so a bare grep
happily returns a hostname that is already dead.

The tunnel is a compose service, so that one command starts it alongside the
API. A quick tunnel needs no Cloudflare account. The URL changes every time the
tunnel container restarts; `ngrok` free includes one stable subdomain if the
re-pasting gets tiring.

CORS already allows any `*.vercel.app` origin via `CORS_ORIGIN_REGEX`, so there
is nothing to configure for a Vercel frontend.

**2. Deploy the frontend**

```bash
cd frontend
npx vercel deploy --prod --yes -b VITE_API_URL="$(cd .. && docker compose logs tunnel \
  | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)"
```

`-b` passes the tunnel URL as a build-time variable, so it is baked into the
bundle.

**3. Turn off Vercel's deployment protection**

New Vercel projects are private by default — anyone but you gets bounced to a
Vercel login page. Dashboard → your project → Settings → Deployment Protection
→ Vercel Authentication → **Disabled**.

Leave it on if only you are opening the link.

**When the tunnel URL changes** you do not need to redeploy: open the site,
expand **API:** on the login screen, paste the new URL, press Enter. It is saved
in that browser. `?api=https://…` in the address bar does the same thing.

**If every request fails with Cloudflare error 1033**, the tunnel process is
alive but never connected -- `docker compose ps` will still say `Up`. Check for
`failed to dial to edge with quic` in the tunnel logs; that means the network is
dropping UDP. The compose file already pins `--protocol http2` to avoid it.

**While demoing:** both containers have to stay running. Close the laptop and
the demo dies.
---

## Your data

Everything lives in `./data` on the host:

```
data/gst_platform.db                  every client, case, message, audit row
data/storage/clients/<id>/<gstin>/…   every uploaded document, every version
```

Verified: `docker compose down` and back up keeps all of it — the container is
disposable, `./data` is not. It is gitignored, so **back it up yourself**; there
is no other copy.

Start completely fresh:

```bash
docker compose down
rm -rf data
docker compose up -d --build      # re-seeds the test accounts
```

---

## Before anyone real uses this

- `SECRET_KEY` in `docker-compose.yml` is the published dev default. Change it,
  and everyone gets signed out.
- A tunnel makes your laptop reachable from the internet. Only run it during a
  demo, and remember the seeded accounts all use `test123`.
- No HTTPS on the container itself; the tunnel provides it.
- No migrations — a model change still needs the database rebuilt.
