# KukuTrack - Poultry Management System for Kenya

Offline-first PWA + FastAPI backend for layer, broiler and improved-kienyeji farms.

## Features implemented
| Area | What's in the code |
|---|---|
| Accounts & roles | Phone+password auth (scrypt, JWT), owner / manager / worker / vet, staff management, login throttling |
| Farm setup | Houses, flocks (layer/broiler/kienyeji), close flock, strict per-farm tenant isolation |
| Daily logs | Eggs, cracked, deaths, feed, water, weight; upsert per flock/day |
| KPIs | Mortality %, hen-day %, FCR (broilers), feed g/bird/day, cost per tray, profit per flock |
| Alerts | High mortality, egg-production drop, vaccination due, low stock |
| Vaccination | Auto-generated schedule per bird type, mark done, hourly SMS reminders (Africa's Talking) |
| Inventory | Feed/drug/other stock, adjust, reorder alerts |
| Finance | Income/expense ledger, chick cost auto-counted, CSV export for banks/SACCOs |
| Offline sync | Queue on device, idempotent `/sync/push` (logs by flock+date, transactions by `client_id`) |
| Feature phones | USSD flow (record eggs/deaths/feed, vaccines due, summary) |
| Billing | 30-day trial, M-Pesa STK push subscription (Daraja), callback extends plan; CSV export is plan-gated |
| Marketplace | Farmers sell eggs/birds/manure/chicks, buyers post wanted ads, suppliers sell feed/drugs/equipment; inquiries with SMS alerts; phone numbers revealed only after the seller accepts; price watch (median per county) |
| Vet consultation | Farmer opens a case with symptoms + up to 5 photos (compressed on the phone); verified vets see all open cases (urgent first) plus the flock's health numbers (never finances), reply, diagnose, close; county-level outbreak counts for early warning |
| Lender report | Owner creates an expiring, revocable share link; SACCO/bank opens a printable report (cash flow, mortality, hen-day, FCR, record-keeping score) with no login |
| Flutter app | `flutter_app/` - login, dashboard, alerts, flocks, daily record with offline queue + auto-sync, vaccinations |
| Account recovery | SMS one-time code password reset (hashed, 10-min expiry, 5 attempts, 3 codes/hour) |
| Data protection | Consent recorded at sign-up, privacy page, owner can download all data (JSON) or permanently delete the account |
| Migrations | Alembic baseline + `entrypoint.sh` runs `alembic upgrade head` on container start |
| UI | English/Kiswahili, installable PWA, service worker |

## Run locally
```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload        # http://localhost:8000  (API docs: /docs)
python -m pytest -q
```
## Production
```bash
cp .env.example .env   # fill secrets
docker compose up -d --build
```
Put it behind HTTPS (Caddy/Nginx/Cloudflare). Webhook URLs to register:
- M-Pesa callback: set automatically to `{PUBLIC_BASE_URL}/api/billing/mpesa/{CALLBACK_SECRET}`
- Africa's Talking USSD callback: `{PUBLIC_BASE_URL}/api/ussd/{CALLBACK_SECRET}`

## Account types & vet verification
Register as `farm`, `buyer`, `supplier` or `vet`. Vet accounts must give a KVB licence number and can do nothing until an admin verifies them:
```bash
docker compose exec api python -m app.jobs.verify_vet 0712345678            # check the licence on the KVB register first!
docker compose exec api python -m app.jobs.verify_vet 0712345678 --revoke
```

## Layout
```
backend/app/  config, db, models, schemas, security, deps
  services/   kpi (pure), vaccination templates, logic, notify (SMS), mpesa
  routers/    auth, operations, reports, lender, market, vet, integrations (sync, billing, USSD)
  jobs/       reminders, verify_vet
backend/tests/  KPI unit tests + API tests
frontend/     index.html (PWA), sw.js, manifest, privacy.html
flutter_app/  Flutter client (see its README)
```

## Database migrations (Alembic)
```bash
cd backend
alembic upgrade head                                  # apply (Docker does this automatically)
alembic revision --autogenerate -m "describe change"  # after editing models.py; review the file!
```
In `ENVIRONMENT=production` the app does **not** call `create_all`, so migrations are required. Dev/test still auto-create tables.

## Before you go live (still open)
1. **Run everything once with real dependencies**: `pytest`, `alembic upgrade head` on Postgres, then `alembic revision --autogenerate -m check` must report *no changes* (proves the hand-written migrations match the models).
2. Sandbox-test M-Pesa, SMS and USSD with real credentials. Compile/run the Flutter app (`flutter analyze`) - it was written without an SDK available.
3. **Marketplace/vet trust & safety**: terms of use, a report/flag button, moderation, and a dispute policy before public launch. Photos are stored on a local volume - back it up or move to object storage (S3/GCS).
4. Lawyer review of `frontend/privacy.html` (now also covers photos, vet sharing and lender links) + ODPC registration; decide payment-record retention.
5. Rate limiting at the gateway; refresh tokens; audit log; backups; Sentry/uptime monitoring.
6. Have a vet review `services/vaccination.py`; the lender score formula is transparent but should be validated with a partner SACCO.
