# Production Portal Launch

## 1. Supabase

- Create the production Supabase project.
- Apply `supabase/migrations/202604250001_svmp_schema.sql`.
- Generate the pooled Postgres connection string for `DATABASE_URL`.
- Record the project URL for `SUPABASE_PROJECT_URL`.
- Confirm the Auth issuer and JWKS URL.

## 2. Backend Vercel Project

Deploy `svmp/` as its own Vercel project.

Set:

- `DATABASE_URL`
- `OPENAI_API_KEY`
- WhatsApp provider secrets
- `DASHBOARD_AUTH_MODE=supabase`
- `DASHBOARD_APP_URL`
- `SUPABASE_PROJECT_URL`
- `SUPABASE_JWT_ISSUER`
- `SUPABASE_JWKS_URL`
- `SUPABASE_JWT_AUDIENCE`
- `CRON_SECRET`
- optionally `INTERNAL_JOB_SECRET`
- Stripe secrets when `BILLING_MODE=stripe`

Notes:

- `svmp/vercel.json` configures the Python function duration and registers cron routes.
- Vercel Cron sends `GET` requests with `Authorization: Bearer <CRON_SECRET>`.

## 3. Portal Vercel Project

Deploy `web/` as its own Vercel project.

Set:

- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_PORTAL_AUTH_MODE=supabase`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
- `NEXT_PUBLIC_BILLING_MODE`

Do not enable preview auth in production.

## 4. Seed Production Access

Before inviting real users:

1. Seed the tenant record with `scripts/seed_tenant.py`.
2. Seed the knowledge base with `scripts/seed_knowledge_base.py`.
3. Seed at least one owner membership with `scripts/seed_portal_access.py`.

## 5. Cutover Checks

- backend `/health` returns `200`
- portal login completes through Supabase
- `/api/me` resolves the correct tenant and role
- billing checkout creation works for an owner
- webhook verification passes for the configured provider
- a live inbound message is answered or escalated end to end
- Vercel cron runs appear in backend runtime logs

## 6. After Launch

- review governance logs daily during the first launch window
- confirm subscription state sync after first Stripe events
- monitor session backlog drain counts from `/internal/jobs/process-ready-sessions`
- keep onboarding limited until it is moved to a durable worker path
