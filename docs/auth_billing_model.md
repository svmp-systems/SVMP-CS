# Auth And Billing Model

## Purpose

This document defines how users, tenant access, roles, and subscriptions should work for the SVMP customer portal.

The main goal is tenant isolation. A signed-in user should only see data for the SVMP tenant connected to their MongoDB verified user record.

## Identity Layers

SVMP uses three separate concepts:

```text
User             -> a human signing in through Clerk
Tenant           -> the SVMP tenantId used in MongoDB
Subscription     -> manually approved billing state for pilots, payment-provider state later
```

The important mapping is:

```text
Clerk user id/email -> verified_users -> SVMP tenantId
```

The browser should not choose this mapping.

## Authentication

Users sign in through Clerk.

Required login methods:

- Google OAuth
- email fallback

The backend verifies Clerk-issued auth on every dashboard API request.

## Tenant Resolution

Every dashboard API request should resolve the tenant in this order:

1. Verify the user auth token.
2. Read the Clerk user id and verified email.
3. Look up the user's active or invited `verified_users` record.
4. Load the tenant, role, and permissions from that record.
5. Load the tenant subscription status.
6. Continue only if role and subscription checks pass.

No dashboard API should accept trusted `tenantId` input from the browser.

## Roles

### Owner

Can manage:

- billing
- team
- integrations
- knowledge base
- brand voice
- settings
- sessions
- metrics
- governance

### Admin

Can manage:

- integrations
- knowledge base
- brand voice
- sessions
- metrics
- governance

Cannot manage:

- billing
- owner-level team controls

### Analyst

Can view:

- sessions
- governance
- metrics

Cannot edit:

- knowledge base
- brand voice
- integrations
- billing
- tenant settings

### Viewer

Can view read-only dashboard data.

Cannot edit tenant configuration or billing.

## Subscription Status

Subscription state is stored in MongoDB. For pilots, SVMP manually marks a tenant as `trialing` or `active` after payment is accepted.

Recommended statuses:

```text
trialing
active
past_due
canceled
unpaid
incomplete
none
```

Operational portal access should require:

```text
trialing or active
```

When subscription is inactive, users should only see billing recovery screens and enough tenant context to understand what happened.

## Manual Pilot Billing Rules

During pilots, SVMP does not require a payment gateway.

Manual approval is the source of truth for subscription activation.

Rules:

- accept payment outside the app
- update `billing_subscriptions.status` to `active` or `trialing`
- mirror current billing status onto the tenant document as a dashboard summary
- do not activate access from a frontend-only action

Payment gateway rules for Stripe/Razorpay can be re-enabled later:

- verify webhook signatures
- store provider event ids in `provider_events`
- process events idempotently
- update `billing_subscriptions`

## Mongo Collections

### `verified_users`

Purpose: connect authenticated users to SVMP tenants and roles.

Shape:

```json
{
  "tenantId": "stay",
  "authProvider": "clerk",
  "providerUserId": "user_123",
  "email": "owner@stayparfums.com",
  "role": "owner",
  "permissions": ["read", "write", "admin"],
  "status": "active",
  "createdAt": "ISODate",
  "updatedAt": "ISODate"
}
```

Indexes:

- unique `authProvider`, `providerUserId`
- `email`, `status`
- `tenantId`, `role`

### `billing_subscriptions`

Purpose: store manual or provider subscription state by tenant.

Shape:

```json
{
  "tenantId": "stay",
  "status": "active",
  "currentPeriodEnd": "ISODate",
  "priceId": "price_123",
  "createdAt": "ISODate",
  "updatedAt": "ISODate"
}
```

Indexes:

- unique `tenantId`
- optional provider customer/subscription ids when a gateway is enabled

### `integration_status`

Purpose: show setup and health status for WhatsApp and future integrations.

Shape:

```json
{
  "tenantId": "stay",
  "provider": "whatsapp",
  "status": "connected",
  "health": "healthy",
  "lastInboundAt": "ISODate",
  "lastOutboundAt": "ISODate",
  "setupWarnings": [],
  "metadata": {},
  "createdAt": "ISODate",
  "updatedAt": "ISODate"
}
```

Indexes:

- unique `tenantId`, `provider`

### `audit_logs`

Purpose: record administrative changes made in the dashboard.

Shape:

```json
{
  "tenantId": "stay",
  "actorUserId": "user_123",
  "actorEmail": "owner@stayparfums.com",
  "action": "knowledge_base.updated",
  "resourceType": "knowledge_base",
  "resourceId": "faq_123",
  "before": {},
  "after": {},
  "timestamp": "ISODate"
}
```

Indexes:

- `tenantId`, `timestamp`
- `tenantId`, `action`
- `tenantId`, `resourceType`, `resourceId`

### `provider_events`

Purpose: make provider webhooks idempotent.

Shape:

```json
{
  "provider": "stripe",
  "eventId": "evt_123",
  "eventType": "customer.subscription.updated",
  "tenantId": "stay",
  "processedAt": "ISODate",
  "payloadHash": "sha256..."
}
```

Indexes:

- unique `provider`, `eventId`
- `tenantId`, `processedAt`

## Tenant Document Extensions

The `tenants` document should eventually include:

```json
{
  "tenantId": "stay",
  "tenantName": "Stay Parfums",
  "websiteUrl": "https://stayparfums.com",
  "industry": "Fragrance",
  "supportEmail": "support@stayparfums.com",
  "brandVoice": {
    "tone": "Warm, polished, premium",
    "use": ["concise", "helpful", "confident"],
    "avoid": ["overpromising", "slang"],
    "escalationStyle": "Apologetic and clear"
  },
  "settings": {
    "confidenceThreshold": 0.75,
    "autoAnswerEnabled": true
  },
  "billing": {
    "status": "active"
  },
  "onboarding": {
    "status": "completed",
    "steps": {
      "profile": true,
      "brandVoice": true,
      "knowledgeBase": true,
      "whatsapp": true,
      "testConversation": true
    }
  }
}
```

The canonical billing state should still live in `billing_subscriptions`; the tenant-level billing object is a fast dashboard summary.

## Backend Dependencies

Dashboard routes should eventually use dependencies like:

```python
require_user()
require_tenant_context()
require_role(["owner", "admin"])
require_active_subscription()
```

The route handler should receive an already-resolved context and should not parse auth or tenant ownership manually.

## Production Requirements

Before paid users rely on the portal:

- verify Clerk auth on every dashboard API
- enforce role permissions on the backend
- enforce subscription status on the backend
- scope every query by resolved tenant
- write audit logs for KB, brand voice, settings, integrations, and billing-sensitive changes
- handle manual billing activation safely
- handle payment-provider webhooks idempotently when a gateway is enabled
- handle provider webhooks idempotently
- avoid storing provider credentials in plain text
- add error states, loading states, and empty states in the UI
- add monitoring and structured logging
