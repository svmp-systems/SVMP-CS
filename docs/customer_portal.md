# Customer Portal

## Stack

- Next.js App Router in `web/`
- Supabase Auth with `@supabase/ssr`
- Backend API calls authenticated with Supabase bearer tokens
- Vercel deployment target

## Auth Modes

Production mode:

- `NEXT_PUBLIC_PORTAL_AUTH_MODE=supabase`
- Supabase handles sign-in, sign-up, OAuth, and session refresh
- the backend resolves memberships and tenant scope

Preview mode:

- `NEXT_PUBLIC_PORTAL_AUTH_MODE=preview`
- guarded by explicit preview env vars
- intended only for temporary demos or internal review

## Request Flow

1. The browser signs in with Supabase.
2. Middleware refreshes the Supabase session when needed.
3. Server components and route handlers read the current Supabase session.
4. Browser and server API clients forward the access token to FastAPI.
5. FastAPI verifies the token and resolves the tenant context from Postgres.

## Portal Surfaces

- `/login`
  Supabase login and magic-link entry
- `/signup`
  Supabase signup and invite-friendly entry
- `/dashboard`
  tenant metrics, recent activity, and setup warnings
- `/sessions`
  session history and governance-linked detail views
- `/settings`
  tenant profile, brand voice, integrations, and billing actions

## Security Boundaries

- The portal never sends a tenant id to choose account scope.
- All privileged mutations depend on backend role checks.
- Integration responses are redacted before being returned to the UI.
- Billing links are created only by backend endpoints.

## Deployment Notes

- Deploy `web/` as its own Vercel project.
- Set `NEXT_PUBLIC_API_BASE_URL` to the backend Vercel URL.
- Set the Supabase publishable key and project URL in the portal project.
- Keep preview auth disabled in production.
