# SVMP

SVMP is a governed AI customer-service platform for WhatsApp support. This repository contains a FastAPI backend in `svmp/`, a Next.js portal in `web/`, and the Postgres schema in `supabase/`.

## Repository layout

- `svmp/` - FastAPI backend for webhook intake, workflows, dashboard APIs, billing, onboarding, and internal job routes
- `web/` - Next.js portal using Supabase Auth or local preview auth
- `supabase/` - SQL migrations for the shared Postgres schema
- `scripts/` - seed and verification utilities
- `docs/` - product and runtime notes

For the current system requirements, see [requirements.md](requirements.md). For the runtime topology, see [system_architecture.md](system_architecture.md).

## Prerequisites

- Python `3.11+`
- Node.js `22.x`
- `npm`
- PostgreSQL or Supabase Postgres
- an OpenAI API key

If you want the real authenticated portal flow, you also need a Supabase project.

## Local setup options

There are two practical ways to run the project locally:

1. `Portal preview only`
   Runs the Next.js app with local preview auth and sample data. This is the fastest way to inspect the UI.
2. `Full stack`
   Runs the FastAPI backend, Postgres-backed data model, and the real Supabase-authenticated portal.

## Option 1: Portal preview only

This mode does not require Postgres, Supabase auth, or the backend API.

1. Copy `web/.env.example` to `web/.env.local`.
2. Change the auth settings in `web/.env.local`:

```env
NEXT_PUBLIC_PORTAL_AUTH_MODE=preview
PORTAL_ALLOW_UNSAFE_PREVIEW_AUTH=true
PORTAL_PREVIEW_PASSWORD=change-me
PORTAL_PREVIEW_AUTH_SECRET=replace-with-a-long-random-string
PORTAL_PREVIEW_ALLOWED_EMAILS=you@example.com
PORTAL_PREVIEW_TENANT_ID=stay
PORTAL_PREVIEW_TENANT_NAME=Stay Parfums
```

3. Install and start the portal:

```powershell
Set-Location web
npm ci
npm run dev
```

4. Open `http://127.0.0.1:3000`.

## Option 2: Full local stack

### 1. Create the Python environment

From the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Provision Postgres and apply the schema

You can use a Supabase project or any PostgreSQL instance that supports `pgcrypto`.

Apply the migration in `supabase/migrations/202604250001_svmp_schema.sql` with your preferred tool. For example:

```powershell
psql "<DATABASE_URL>" -f supabase/migrations/202604250001_svmp_schema.sql
```

### 3. Configure the backend

Copy `.env.example` to `.env`, then replace the production placeholders with local values.

For a minimal local backend, these are the important changes:

```env
APP_ENV=development
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/svmp
OPENAI_API_KEY=your-openai-key

WHATSAPP_PROVIDER=normalized
ALLOW_NORMALIZED_WEBHOOKS=true

DASHBOARD_AUTH_MODE=supabase
SUPABASE_PROJECT_URL=https://your-project-ref.supabase.co
DASHBOARD_APP_URL=http://127.0.0.1:3000
DASHBOARD_CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000

BILLING_MODE=manual
```

Notes:

- `SUPABASE_JWT_ISSUER` and `SUPABASE_JWKS_URL` can be omitted if `SUPABASE_PROJECT_URL` is set.
- If you want to test internal job routes locally, also set `INTERNAL_JOB_SECRET` or `CRON_SECRET`.
- If you want live Meta or Twilio webhooks, switch `WHATSAPP_PROVIDER` and fill in the matching provider credentials instead of using `normalized`.

### 4. Start the backend

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn svmp_core.main:app --app-dir svmp --reload --host 127.0.0.1 --port 8000
```

The healthcheck is available at `http://127.0.0.1:8000/health`.

### 5. Seed sample tenant data

In a second shell from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\seed_tenant.py
python scripts\seed_knowledge_base.py
python scripts\seed_portal_access.py --tenant-id stay --email you@example.com --subscription-status active
```

`seed_portal_access.py` can create an email invite without a Supabase user id. When you later sign in to the portal with the same email, the backend can attach that invite to the authenticated user.

### 6. Configure the portal

Copy `web/.env.example` to `web/.env.local`, then set the local backend URL and your Supabase values:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_PORTAL_AUTH_MODE=supabase
NEXT_PUBLIC_SUPABASE_URL=https://your-project-ref.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your-supabase-publishable-key
NEXT_PUBLIC_BILLING_MODE=manual
```

### 7. Start the portal

```powershell
Set-Location web
npm ci
npm run dev
```

Open `http://127.0.0.1:3000`, sign in with Supabase, and use the same email you seeded in the previous step.

### 8. Optional webhook smoke test

With `WHATSAPP_PROVIDER=normalized`, you can post a trusted normalized payload directly to the backend:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/webhook `
  -ContentType "application/json" `
  -Body '{"tenantId":"stay","clientId":"whatsapp","userId":"demo-user-001","text":"Do you offer free shipping?"}'
```

The backend will ingest the message, wait for the debounce window, and attempt Workflow B inline.

## Validation commands

Backend import smoke:

```powershell
.\.venv\Scripts\python.exe -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path('svmp').resolve())); from svmp_core.main import create_app; print(callable(create_app))"
```

Backend tests:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="svmp"
python -m pytest svmp/tests
```

Frontend typecheck:

```powershell
Set-Location web
npm run typecheck
```

Live runtime verification against your configured database and OpenAI key:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\verify_live_runtime.py --tenant-id stay
```

## Related docs

- [requirements.md](requirements.md)
- [system_architecture.md](system_architecture.md)
- [docs/customer_portal.md](docs/customer_portal.md)
- [docs/provider_connection.md](docs/provider_connection.md)
