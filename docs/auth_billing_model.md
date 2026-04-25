# Auth And Billing Model

## Core Principles

- Supabase Auth is the only production identity provider for the portal.
- The browser never chooses its tenant boundary.
- Billing state is enforced by the backend, not trusted from the frontend.
- Postgres is the source of truth for memberships, tenant metadata, and subscription state.

## Auth Flow

1. The portal signs users in with Supabase Auth.
2. The Next.js app reads the Supabase session through `@supabase/ssr`.
3. API calls include the Supabase access token as a bearer token.
4. The FastAPI backend verifies the JWT against the configured Supabase issuer and JWKS.
5. The backend resolves tenant access from `tenant_memberships`.

The JWT is used only for identity. Tenant access, role, and billing state come from backend-owned records.

## Membership Model

`tenant_memberships` stores:

- `tenant_id`
- `auth_provider`
- `provider_user_id`
- `email`
- `organization_id`
- `role`
- `permissions`
- `status`

The backend resolves one effective `TenantContext` from that table and then applies:

- role checks for write operations
- subscription checks for operational reads
- tenant scoping for all dashboard data

## Billing Model

Two records participate in billing enforcement:

- `billing_subscriptions` stores Stripe-linked subscription state
- `tenants.payload` and tenant billing fields expose the current effective billing summary

Operational endpoints require an active or trialing subscription. Billing recovery endpoints remain owner-only but can still be used when the tenant is `past_due` or otherwise inactive.

## Stripe Behavior

- Checkout sessions are created server-side only.
- Portal sessions are created server-side only.
- Stripe webhooks are verified with the configured webhook secret.
- Provider events are recorded idempotently in `provider_events`.
- Subscription updates are written back to both `billing_subscriptions` and tenant billing fields.

## Production Notes

- `DASHBOARD_AUTH_MODE` should be `supabase` in production.
- Preview auth is for temporary non-production demos only.
- Tenant membership seeding should happen before inviting real users into the portal.
- If Vercel Cron is used, `CRON_SECRET` should be configured on the backend project and should match the secret accepted by internal job routes.
