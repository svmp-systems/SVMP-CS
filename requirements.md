# SVMP Requirements

This document describes the current system requirements for the code in this repository. It is meant to complement [system_architecture.md](system_architecture.md).

## Product scope

SVMP is a governed AI customer-service platform for WhatsApp support. The current codebase supports:

- inbound WhatsApp webhook intake
- session debouncing and batching
- knowledge-base matching plus OpenAI-assisted response generation
- governance logging for answer and escalation decisions
- a customer portal for tenant setup, sessions, metrics, knowledge base, brand voice, integrations, and billing

## System shape

The repository is split into three primary runtime surfaces:

- `svmp/`
  FastAPI backend for webhook handling, dashboard APIs, billing endpoints, onboarding flows, and internal job routes
- `web/`
  Next.js App Router portal that authenticates users and calls the backend API
- `supabase/`
  Postgres schema migrations used by both the backend and the portal

Operational scripts live in `scripts/`, and supporting notes live in `docs/`.

## Runtime model

The current backend behavior is:

1. Workflow A ingests inbound messages into `session_state`.
2. The backend waits for the session debounce window.
3. Workflow B attempts to answer from approved knowledge or escalates.
4. Governance decisions are written to `governance_logs`.
5. Internal job routes remain available to drain backlog and clean stale sessions.

The current portal behavior is:

- production auth is Supabase-backed
- preview auth exists only for local review and temporary demos
- tenant scope is resolved server-side from memberships, not from client-submitted tenant ids

## Runtime dependencies

### Required for the backend

- Python `3.11+`
- PostgreSQL reachable through `DATABASE_URL`
- `pgcrypto` enabled in the database
- an `OPENAI_API_KEY`

### Required for any portal run

- Node.js `22.x` and `npm`

### Required for the portal to call the backend

- `NEXT_PUBLIC_API_BASE_URL` pointing at the backend

### Required for full authenticated portal usage

- a Supabase project
- `SUPABASE_PROJECT_URL` on the backend
- `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` in `web/`

### Optional integrations

- Meta WhatsApp credentials when `WHATSAPP_PROVIDER=meta`
- Twilio WhatsApp credentials when `WHATSAPP_PROVIDER=twilio`
- Stripe credentials when `BILLING_MODE=stripe`

For trusted local testing, the backend can run with `WHATSAPP_PROVIDER=normalized` and `ALLOW_NORMALIZED_WEBHOOKS=true` instead of live provider credentials.

## Configuration requirements by capability

### Core backend

These settings are required for a real backend boot:

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `WHATSAPP_PROVIDER`

If the portal will call the backend from a browser origin, set one of:

- `DASHBOARD_APP_URL`
- `DASHBOARD_CORS_ORIGINS`

### Dashboard auth

For the real portal experience, the backend must run with:

- `DASHBOARD_AUTH_MODE=supabase`
- `SUPABASE_PROJECT_URL`

`SUPABASE_JWT_ISSUER` and `SUPABASE_JWKS_URL` are optional overrides. If they are omitted, the backend derives them from `SUPABASE_PROJECT_URL`.

### Webhook provider modes

- `meta`
  Requires `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, and `META_APP_SECRET`
- `twilio`
  Requires `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_WHATSAPP_NUMBER`
- `normalized`
  Intended for trusted local tools and tests; use `ALLOW_NORMALIZED_WEBHOOKS=true` or set `NORMALIZED_WEBHOOK_SECRET`

### Billing

- `BILLING_MODE=manual`
  No Stripe secrets required
- `BILLING_MODE=stripe`
  Requires `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and `STRIPE_PRICE_ID`

### Internal job routes

The internal job endpoints require `INTERNAL_JOB_SECRET` or `CRON_SECRET` when they are actually invoked. In production, one of these secrets is mandatory.

## Data requirements

The application depends on the schema in `supabase/migrations/202604250001_svmp_schema.sql`, including:

- `tenants`
- `tenant_memberships`
- `tenant_provider_identities`
- `session_state`
- `knowledge_base_entries`
- `governance_logs`
- `integration_status`
- `audit_logs`
- `billing_subscriptions`
- `provider_events`

The current model assumes:

- one open session per tenant/client/user identity
- provider identity mappings are unique per provider identity
- portal access is resolved from `tenant_memberships`
- provider events are stored idempotently

## Deployment requirements

The codebase currently supports two deployment shapes:

- stateless Vercel-style deployment for the backend, including cron registration via `svmp/vercel.json`
- container deployment for both services via `svmp/Dockerfile` and `web/Dockerfile`

In both cases, the backend and portal share the same Postgres data plane.

## Known constraints

- outbound Meta/Twilio credentials are still runtime-wide environment variables, not per-tenant secrets
- preview auth is for local or temporary review only, not production
- the backend validates required runtime configuration at startup, so placeholder values in `.env.example` must be replaced before booting a real stack
