# Production Portal Launch

## Goal

The customer portal should be private by default. A user must sign in through Clerk, map to one SVMP tenant through MongoDB `verified_users`, and pass backend role/subscription checks before any tenant data is returned.

## Frontend Env

Set these in Vercel for the customer portal:

```text
NEXT_PUBLIC_PORTAL_AUTH_MODE=clerk
NEXT_PUBLIC_API_BASE_URL=https://api.svmpsystems.com
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
CLERK_SECRET_KEY=sk_live_...
CLERK_JWT_TEMPLATE=svmp-dashboard
NEXT_PUBLIC_CLERK_JWT_TEMPLATE=svmp-dashboard
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/login
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/signup
```

The Clerk JWT template should include the Clerk user id and email claim. Email is required only when you seed an invite before you know the Clerk user id.

Do not enable preview auth for paid-client production access:

```text
PORTAL_ALLOW_UNSAFE_PREVIEW_AUTH=false
```

## Backend Env

Set these on the FastAPI host:

```text
APP_ENV=production
DASHBOARD_AUTH_MODE=clerk
DASHBOARD_APP_URL=https://app.svmpsystems.com
DASHBOARD_CORS_ORIGINS=https://svmp-cs.vercel.app,https://app.svmpsystems.com
CLERK_ISSUER=https://your-clerk-issuer
CLERK_JWKS_URL=https://your-clerk-issuer/.well-known/jwks.json
CLERK_AUDIENCE=svmp-dashboard
BILLING_MODE=manual
```

Keep the existing MongoDB, OpenAI, and WhatsApp provider secrets configured too.

Stripe is not required for pilots. Paid access is manually accepted by setting the tenant subscription status to `active` or `trialing` in MongoDB.

## Access Setup

1. Create the tenant document in MongoDB.
2. Add or invite the user in Clerk.
3. Copy the Clerk user id when available.
4. Seed the backend verified user access:

```powershell
& .\.venv\Scripts\python.exe .\scripts\seed_portal_access.py `
  --tenant-id stay `
  --provider-user-id user_... `
  --email prnvvh@gmail.com `
  --role owner `
  --subscription-status active
```

The browser never sends or chooses `tenantId`. The backend resolves it from `verified_users`.

You do not need to manually create `verified_users` in MongoDB first. MongoDB creates it on first insert, and the backend also creates indexes for it on startup.

For an email invite before the user has a Clerk id, omit `--provider-user-id`; the script creates an `invited` record. On first login, the backend binds the Clerk user id and marks the record active.

For manual pilots, the same command can mark the tenant active with:

```powershell
--subscription-status active
```

That writes/updates `billing_subscriptions` and mirrors `billing.status` on the tenant document.

## Sanity Checks

- Incognito `/dashboard` redirects to `/login`.
- Login works inside `/login`, not by directly opening a public dashboard.
- `/api/me` returns exactly one tenant context.
- Dashboard API requests include a Clerk bearer token.
- FastAPI rejects dashboard API requests without auth.
- Operational APIs return `402` when manual subscription status is not `active` or `trialing`.
- KB, brand voice, settings, and WhatsApp edits create audit logs.
