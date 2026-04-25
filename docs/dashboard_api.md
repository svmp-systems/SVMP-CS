# Dashboard API

## Authentication

All dashboard endpoints live under `/api`.

Production requests must:

- send `Authorization: Bearer <supabase-access-token>`
- use `DASHBOARD_AUTH_MODE=supabase`

The backend verifies the token and resolves tenant access from `tenant_memberships`.

## Read Endpoints

- `GET /api/me`
  authenticated user summary, resolved tenant, role, and allowed actions
- `GET /api/tenant`
  tenant profile without trusting frontend tenant selection
- `GET /api/overview`
  overview metrics, recent activity, setup warnings, system health
- `GET /api/metrics`
  decision counts and deflection rate
- `GET /api/sessions`
  recent tenant sessions
- `GET /api/sessions/{session_id}`
  session transcript plus related governance logs
- `GET /api/knowledge-base`
  tenant FAQ entries
- `GET /api/brand-voice`
  current tenant brand-voice payload
- `GET /api/governance`
  governance decisions
- `GET /api/integrations`
  safe integration status view with redaction

## Write Endpoints

- `PATCH /api/tenant`
  owner/admin only
- `POST /api/knowledge-base`
  owner/admin only
- `PATCH /api/knowledge-base/{entry_id}`
  owner/admin only
- `DELETE /api/knowledge-base/{entry_id}`
  owner/admin only
- `PATCH /api/brand-voice`
  owner/admin only
- `PATCH /api/integrations/whatsapp`
  owner/admin only and rejects secret-bearing payloads

## Billing Endpoints

- `POST /api/billing/create-checkout-session`
  owner only, subscription check intentionally bypassed for recovery
- `POST /api/billing/create-portal-session`
  owner only
- `POST /api/billing/webhook`
  Stripe webhook receiver

## Internal Jobs

- `GET|POST /internal/jobs/process-ready-sessions`
- `GET|POST /internal/jobs/cleanup-stale-sessions`

These routes accept either:

- `Authorization: Bearer <CRON_SECRET>`
- `Authorization: Bearer <INTERNAL_JOB_SECRET>`
- `X-SVMP-Job-Secret: <secret>`

`GET` support exists specifically so Vercel Cron can invoke the routes directly.
