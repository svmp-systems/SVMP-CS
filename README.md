# SVMP

SVMP is a governed AI customer-service platform for WhatsApp support. The system is now structured around Supabase and Vercel: Supabase provides Postgres, Auth, and cron-friendly infrastructure, while the backend and portal are designed for stateless Vercel deployments.

## Architecture

- `svmp/`
  FastAPI backend for webhook intake, workflows, dashboard APIs, billing, and internal cron-triggered job endpoints.
- `web/`
  Next.js customer portal using Supabase Auth SSR helpers and bearer-token calls into the backend API.
- `supabase/`
  SQL migrations for the Postgres schema backing tenants, memberships, sessions, knowledge base entries, governance logs, billing, and provider-event idempotency.
- `scripts/`
  Operational and seed utilities that should target Supabase/Postgres-backed data.
- `docs/`
  Product, deployment, and runtime notes.

## Runtime Flow

1. A WhatsApp webhook lands on the FastAPI backend.
2. Workflow A writes or updates the active session window in Postgres.
3. A stateless internal job endpoint processes ready sessions through Workflow B.
4. Cleanup runs through a second internal job endpoint for Workflow C.
5. Governance, billing, and dashboard reads all come from the same Supabase-backed data model.

## Deployment Shape

- Deploy `web/` to Vercel as the customer portal project.
- Deploy `svmp/` to Vercel as a separate Python/FastAPI project.
- Use the Supabase pooled Postgres URL for `DATABASE_URL`.
- Use Supabase Auth for portal sign-in and JWT verification.
- Use `svmp/vercel.json` to register the backend cron routes on Vercel.
- Set `CRON_SECRET` in the backend Vercel project. The backend accepts either `CRON_SECRET` or `INTERNAL_JOB_SECRET` for internal job authentication.
- Keep `/internal/jobs/process-ready-sessions` enabled as a backstop drain path even though webhook intake now attempts best-effort inline Workflow B execution.

## Quick Validation

Backend import smoke:

```bash
.venv\Scripts\python.exe -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path('svmp').resolve())); from svmp_core.main import create_app; print(callable(create_app))"
```

Frontend typecheck:

```bash
cd web
npm run typecheck
```
