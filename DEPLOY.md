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

brew install cloudflared
cloudflared tunnel --url http://localhost:8010
#  -> https://random-words-1234.trycloudflare.com
```

That URL only lives as long as the command runs, and you get a new one each
time. `ngrok http 8010` works the same way; its free tier includes one stable
subdomain, which saves re-pasting.

**2. Let the tunnel origin through CORS**

Edit `docker-compose.yml` → `CORS_ORIGINS`, adding your Vercel URL:

```yaml
CORS_ORIGINS: "http://localhost:5173,https://your-app.vercel.app"
```

Then `docker compose up -d` again. Vercel preview deployments are already
covered by the `CORS_ORIGIN_REGEX` entry.

**3. Deploy the frontend**

```bash
cd frontend
npx vercel            # root directory: frontend
```

Set `VITE_API_URL` in Vercel's environment variables to the tunnel URL, and
redeploy so it is baked into the build.

**Or skip that entirely:** open the deployed site and expand **API:** on the
login screen, paste the tunnel URL, press Enter. It is saved in that browser, so
when the tunnel URL changes you re-paste instead of redeploying. `?api=https://…`
in the address bar does the same thing.

**When the tunnel URL changes**, you do not need to redeploy: open the site,
expand **API:** on the login screen, paste the new URL, press Enter.

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
