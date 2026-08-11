# GST Monthly Compliance Management System — Stage 1

One platform, two portal experiences (client + CA/admin), one shared backend.

```
CLIENT PORTAL ─┐                    ┌─ SQLite (dev) → Postgres/Firebase later
               ├─ FastAPI backend ──┼─ Local disk (dev) → Firebase Storage later
CA PORTAL   ───┘                    └─ Workflow engine · audit · messaging
```

**The portal is the system of record for the firm. The GST portal remains the system of filing.**

---

## Run it

Docker (keeps data in `./data`, survives rebuilds):

```bash
docker compose up -d --build     # API on http://localhost:8010
cd frontend && npm run dev       # UI  on http://localhost:5173
```

See [DEPLOY.md](DEPLOY.md) for demoing to someone who is not sitting at your
laptop — including why a Vercel frontend cannot reach a backend on localhost.

Or run it directly, two terminals:

```bash
# 1. backend  (http://127.0.0.1:8010, docs at /docs)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python seed.py --reset          # test accounts + masters + sample workbooks
.venv/bin/uvicorn app.main:app --port 8010 --reload

# 2. frontend (http://localhost:5173)
cd frontend
npm install
npm run dev
```

### Test accounts (password `test123`)

| Email | Role | Sees |
|---|---|---|
| `admin@test.com` | CA_ADMIN | everything, can create users/clients/assignments |
| `staff@test.com` | CA_EMPLOYEE | assigned clients only (ABC Enterprises) |
| `client@test.com` | CLIENT | ABC Enterprises only |
| `client2@test.com` | CLIENT | XYZ Traders only |

Google sign-in is deliberately **not** wired up yet — see *Swapping in Firebase* below.

### Sample workbooks

`seed.py` writes three files to `storage/samples/` that exercise the matching engine end to end:

| File | Purpose |
|---|---|
| `gstr1_sales_july_2026.xlsx` | client's GSTR-1 outward data |
| `purchase_register_july_2026.xlsx` | client's Purchase Register (8 invoices) |
| `gstr2b_july_2026.xlsx` | GSTR-2B downloaded by the CA team (7 invoices) |

Reconciling those two produces 4 exact matches, 1 partial (date drift), 1 mismatch (value differs),
2 missing in GSTR-2B and 1 missing in the Purchase Register.

---

## What Stage 1 does

**Masters** — Client → File. A **file is one GST registration**: the GSTIN lives on the file, so a
client with two GSTINs has two files. Compliance months hang off the file.

A client is a name, a phone number and **one login**, created together by an admin — a client
without a login could never reach their own portal. The email and password live on the linked
`User`, so there is a single copy of the login and it cannot drift.

**Monthly compliance** — opening a month for a GSTIN creates a `ComplianceCase` with three
`ReturnItem` tracks: GSTR-1, GSTR-2B reconciliation, GSTR-3B.

**Documents** — never overwritten. Every upload is a new `DocumentVersion` with uploader, timestamp,
size, checksum and an *uploaded on behalf of client* flag so CA staff can upload for the client.

**Workflow** — one status machine (`app/services/workflow.py`), six states, drives all three tracks:

| Track | Chain | Ends at |
|---|---|---|
| GSTR-1 | `AWAITING_CLIENT_DATA → CLIENT_DATA_SUBMITTED → UNDER_CA_REVIEW → VERIFIED → FILED` | `FILED` |
| Purchase recon | `AWAITING_CLIENT_DATA → CLIENT_DATA_SUBMITTED → UNDER_CA_REVIEW → VERIFIED` | `VERIFIED` |
| GSTR-3B | `UNDER_CA_REVIEW → AWAITING_PAYMENT → VERIFIED → FILED` | `FILED` |

There is deliberately no query/revision/resubmit state. All of that happens inside
`UNDER_CA_REVIEW`: the client keeps uploading new versions and replying in the discussion until the
CA signs off. **"Who are we waiting on" is derived** — an unanswered query means the client, nothing
else does — so it never gets out of step with reality.

Illegal hops return 409, wrong-role hops return 403, states outside a track's own chain return 409
(the reconciliation can never be `FILED`), and every hop writes a `StatusTransition` plus an audit
row. GSTR-3B stays blocked, with a `blocked_reason` instead of actions, until GSTR-1 is filed and
the reconciliation is finalised.

Clients see three states only — **Your turn**, **With your CA team**, **Done** — and never the
internal ones.

**Communication** — one discussion per stage, created automatically. Nobody picks or names a thread.
A CA message can be ticked *Needs client action* (optionally *Corrected file required*); the client
simply replies, and that reply answers it. The stage never leaves `UNDER_CA_REVIEW` — only the
derived "waiting on" flips. CA-only internal notes are hidden from clients. Mismatched invoices get the
same compact discussion inline on their row. The sidebar's **Needs attention** page is a flat list of
open items with a deep link to the stage — not a message browser.

**Reconciliation** — a four-pass deterministic matcher, not a VLOOKUP:

| Pass | Key | Result |
|---|---|---|
| 1 | GSTIN + normalised invoice no + date | `EXACT_MATCH`, or `MISMATCH` with per-field diff flags |
| 2 | GSTIN + invoice no (date within tolerance) | `PARTIAL_MATCH` |
| 3 | GSTIN + date + taxable value | `PROBABLE_MATCH` (invoice number differs) |
| 4 | invoice no + date + value | `PROBABLE_MATCH` (supplier GSTIN differs) |
| — | leftovers | `MISSING_IN_2B` / `MISSING_IN_PR` |

Each result row carries its own status, owner, CA remark, client response and resolution — the
mismatch report is a workflow, not a spreadsheet. The client sees the same six categories on their
Purchase matching step, in plain language ("Your supplier has not reported this invoice yet"), and
can download the same Excel workbook the CA team works from.

**GSTR-3B** — no figures are entered into this system at all. The CA reads the return on the GST
portal; uploading a challan is how they say tax is payable, and signing the return off without one
is how they say it is not.

The challan is **a PDF, not a data entry screen**: the CA uploads the file downloaded from the GST
portal, which puts the return into `AWAITING_PAYMENT`. The client downloads it, pays on the portal
and presses *I have paid* — optionally with a reference and a receipt — and that confirmation clears
the return for filing. No amounts, CPIN, CIN or UTR are ever re-keyed into this system.

`FILED` and `AWAITING_PAYMENT` cannot be reached by a bare status change, and neither can
`AWAITING_PAYMENT → VERIFIED`: each needs its real action (an ARN, a challan, a confirmation), so a
status can never claim something happened without the record that proves it.

**Audit trail** — every upload, download, status change, query, reconciliation run, mismatch update,
challan, payment and filing.

### Deliberately not in Stage 1

Portal login/scraping, auto-filing, auto-2B download, auto-challan, OCR, AI extraction, Tally,
WhatsApp/email automation, due-date engine, e-invoice, e-way bill.

---

## Layout

```
backend/app/
  core/        config, db, enums (status machine vocabulary), security
  models/      identity, client, compliance, document, comms, recon, gstr3b, audit
               (gstr3b = payment + filing; the challan and payment proof are
                just Documents)
  services/    workflow, permissions, documents, parser, matching, gstr3b, periods,
               audit, notifications
  storage/     StorageBackend interface + LocalStorage
  api/routes/  auth, masters, cases, documents, queries, conversations, recon,
               gstr3b, dashboard
frontend/src/
  api.ts, auth.tsx
  pages/       Login, ClientDashboard, ClientMonth (stepper), CaDashboard,
               CaseWorkspace, ComplianceGrid, Clients, Messages, AuditTrail
  components/  ui.tsx, Discussion.tsx
storage/       uploaded files (dev) + samples/
```

One URL, two experiences: `/cases/:id` renders `ClientMonth` for a client and `CaseWorkspace` for
CA staff off the same API. The client gets a six-step tracker — sales data, GSTR-1 filed, purchase
register, matching, payment, GSTR-3B filed — each step one line of plain English with at most one
button, and no tabs. CA staff get the tabbed workspace: per-stage document history, the matching
engine, the GSTR-3B control sheet, manual state control and the audit trail.

---

## Swapping in Firebase (Stage 2)

Three seams were built for it; nothing else should need to change.

1. **Storage** — implement `StorageBackend` (`backend/app/storage/base.py`) as `FirebaseStorage`
   and return it from `get_storage()`. The rest of the app only ever handles a `storage_key` string.
2. **Auth** — replace the token decode in `backend/app/api/deps.py::get_current_user` with a Firebase
   ID-token verification that resolves to a `User` row via `external_uid`. The `User` model already
   carries `auth_provider` and `external_uid`. Every route keeps its `Depends(get_current_user)`.
3. **Database** — change `database_url` in `backend/app/core/config.py` to Postgres and introduce
   Alembic (the dev stage uses `Base.metadata.create_all`).

---

## Known dev-stage shortcuts

Intentional, because this is not production yet:

- Hard-coded `secret_key`, password login, no refresh tokens, no rate limiting.
- Sessions live in `sessionStorage`, so each browser tab holds its own login — handy for driving the
  CA and client portals side by side. The trade-off is that a brand-new tab starts signed out.
- `create_all()` instead of migrations — a model change needs `seed.py --reset`.
- SQLite and local disk; file downloads stream through the API rather than signed URLs.
- Notifications are polled, not pushed.
- No file-type/virus validation beyond an extension check on workbooks.
- GST portal integration is entirely manual by design.
