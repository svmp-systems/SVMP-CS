# Dashboard API Contract

## Purpose

Dashboard APIs power the paid customer portal. They live under `/api` in the FastAPI app and are separate from provider webhooks.

Provider webhook:

```text
/webhook
```

Future payment-provider webhook:

```text
/api/billing/webhook
```

## Core Security Rule

Dashboard APIs must never trust `tenantId` from the browser.

Every dashboard request should follow this backend flow:

```text
verify user auth
verify Clerk user identity
resolve SVMP tenantId from MongoDB verified_users
resolve user role
check subscription status when required
run tenant-scoped query
return tenant-scoped response
```

This means browser requests can filter, sort, and paginate tenant data, but cannot choose the tenant boundary.

## Request Context

The backend should derive a request context similar to:

```json
{
  "userId": "clerk-user-id",
  "organizationId": "stay",
  "tenantId": "stay",
  "role": "owner",
  "subscriptionStatus": "active"
}
```

This object is internal to the backend. It should come from auth and database lookups, not from client-submitted JSON.

## Role Matrix

```text
Owner   -> billing, team, integrations, KB, brand voice, settings, sessions, metrics, governance
Admin   -> integrations, KB, brand voice, sessions, metrics, governance
Analyst -> sessions, governance, metrics
Viewer  -> read-only dashboard
```

## Subscription Gate

If the tenant subscription is inactive, dashboard APIs should return only enough data to show billing and payment recovery.

Allowed when inactive:

- `GET /api/me`
- `GET /api/tenant`
- manual pilot billing is activated by backend/Mongo admin action
- `POST /api/billing/create-checkout-session` only when gateway billing is enabled
- `POST /api/billing/create-portal-session` only when gateway billing is enabled

All operational tenant data should require active subscription status.

## Endpoints

### `GET /api/me`

Purpose: return the signed-in user's portal context.

Response includes:

- user id
- email
- access scope id
- tenant id
- role
- subscription status
- onboarding status
- allowed actions

### `GET /api/tenant`

Purpose: return the current tenant profile.

Response includes:

- tenant id
- tenant name
- website URL
- industry
- support email
- settings
- onboarding state
- billing summary

### `PATCH /api/tenant`

Purpose: update tenant profile and settings.

Allowed roles:

- owner
- admin for non-billing settings

Must write an audit log.

### `GET /api/overview`

Purpose: power the main dashboard page.

Response includes:

- deflection rate
- human hours saved
- average resolution time
- safety score
- AI resolved count
- human escalated count
- recent activity
- setup warnings
- system health

### `GET /api/metrics`

Purpose: return deeper analytics.

Response includes:

- automation trend
- escalation trend
- response time by hour
- topic distribution
- volume by day, week, or month
- KB gap insights when available

### `GET /api/sessions`

Purpose: list customer conversations or conversation summaries.

Query support:

- status
- decision
- provider
- date range
- search text
- pagination

Response includes:

- session or conversation id
- customer id
- provider
- status
- latest message
- latest answer
- confidence score
- escalation reason
- timestamp

### `GET /api/sessions/{id}`

Purpose: show one customer conversation.

Response includes:

- identity tuple
- provider
- messages or reconstructed transcript
- SVMP answer
- matched KB source
- confidence score
- governance decisions
- escalation reason
- timestamps

The id must be resolved inside the current tenant only.

### `GET /api/knowledge-base`

Purpose: list KB entries for the current tenant.

Query support:

- domain
- active
- tags
- search
- pagination

### `POST /api/knowledge-base`

Purpose: create a KB entry.

Allowed roles:

- owner
- admin

Must write an audit log.

### `PATCH /api/knowledge-base/{id}`

Purpose: update a KB entry.

Allowed roles:

- owner
- admin

Must write an audit log.

The id must be resolved inside the current tenant only.

### `DELETE /api/knowledge-base/{id}`

Purpose: delete or deactivate a KB entry.

Allowed roles:

- owner
- admin

Preferred MVP behavior: soft delete by setting `active=false`, unless hard delete is explicitly needed.

Must write an audit log.

### `GET /api/brand-voice`

Purpose: return tenant brand voice settings.

Response includes:

- tone
- words to use
- words to avoid
- escalation style
- example replies

### `PATCH /api/brand-voice`

Purpose: update brand voice settings.

Allowed roles:

- owner
- admin

Must write an audit log.

### `GET /api/governance`

Purpose: list governance decisions and trust events.

Query support:

- decision
- confidence range
- provider
- date range
- search
- pagination

Response includes:

- decision
- customer question
- answer supplied
- matched question
- similarity score
- threshold
- reason
- provider
- timestamp

### `GET /api/integrations`

Purpose: show integration status cards.

Response includes:

- WhatsApp connection status
- provider
- health
- last received event
- last outbound send
- setup warnings
- upcoming integrations

### `PATCH /api/integrations/whatsapp`

Purpose: update WhatsApp integration configuration or status.

Allowed roles:

- owner
- admin

Must write an audit log.

The first controlled MVP can use runtime-wide provider credentials, but multi-tenant production needs per-tenant provider credential handling.

### `POST /api/test-question`

Purpose: let a dashboard user preview SVMP against current KB and brand voice without sending a WhatsApp message.

Response includes:

- answer or escalation preview
- matched KB entry
- confidence score
- governance reasoning

This should not create a real customer session.

### `POST /api/billing/create-checkout-session`

Purpose: create a payment checkout session when gateway billing is enabled.

Allowed roles:

- owner

### `POST /api/billing/create-portal-session`

Purpose: create a payment billing portal session when gateway billing is enabled.

Allowed roles:

- owner

### `POST /api/billing/webhook`

Purpose: receive payment-provider subscription events when gateway billing is enabled.

Rules:

- verify provider signature
- store provider event id
- process events idempotently
- update tenant subscription state
- never depend on frontend redirect success to activate access

## Data Source Notes

The current runtime has:

- `session_state`: active debounce and processing state
- `knowledge_base`: trusted FAQ entries
- `governance_logs`: answer, escalation, and closure audit trail
- `tenants`: tenant metadata and routing settings

For dashboard sessions and metrics, `governance_logs` will likely be the strongest initial source because it stores decisions, answers, confidence data, provider data, matched questions, and timestamps.

## Testing Requirements

Minimum API tests:

- unauthenticated requests are rejected
- inactive subscription cannot access operational data
- viewer cannot edit
- analyst cannot edit KB or brand voice
- admin can edit KB and brand voice
- owner can access billing flows
- browser-submitted tenant ids are ignored
- all reads and writes are tenant-scoped
- KB edits write audit logs
- brand voice edits write audit logs
- payment-provider webhook is idempotent when gateway billing is enabled
