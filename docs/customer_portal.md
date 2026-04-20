# SVMP Customer Portal

## Purpose

The customer portal is the private paid-client dashboard for SVMP. It is served at `app.svmpsystems.com` and is separate from any public `svmpsystems.com` marketing or lab site.

The portal should help a business:

- see whether SVMP is live and healthy
- configure how SVMP answers customers
- maintain the knowledge SVMP is allowed to use
- inspect answers, escalations, and governance logs
- understand support savings and safety outcomes
- manage billing, team access, and integrations

## Product Shape

The portal is not a public self-serve SaaS in the first version. It is a private dashboard for paid SVMP clients.

The expected user journey is:

1. A business pays for SVMP.
2. A user signs in.
3. SVMP verifies the user against MongoDB `verified_users`.
4. The verified user record maps to one SVMP `tenantId`.
5. SVMP checks that the tenant has an active subscription.
6. The user configures business profile, brand voice, knowledge base, and WhatsApp.
7. The user monitors conversations, governance, and metrics.

## Recommended Repo Shape

```text
SVMP-CS/
  svmp/        # FastAPI backend, WhatsApp webhook, Mongo workflows
  web/         # customer dashboard frontend
  scripts/
  docs/
```

The current repository already has `svmp/`, `scripts/`, and `docs/`. The `web/` app will be added when the backend contracts are ready.

## Default Stack

- Frontend: Next.js with TypeScript
- Styling: Tailwind CSS with local shadcn/ui-style components
- Charts: Recharts
- Auth: Clerk
- Login: Google OAuth plus email fallback
- Billing: manual pilot approval first; Stripe/Razorpay gateway later
- Backend: existing FastAPI app
- Database: MongoDB Atlas
- Web hosting: Vercel
- API hosting: Render, Railway, Fly, or AWS

## Domains

```text
app.svmpsystems.com -> customer dashboard
api.svmpsystems.com -> FastAPI API and WhatsApp webhook
```

Provider webhooks and billing webhooks must stay distinct:

```text
/webhook                  # WhatsApp provider webhook
/api/billing/webhook      # future payment-provider webhook
```

## MVP Scope

The first paid-client MVP includes:

- Google login
- email login fallback
- paid tenant access check
- verified user to tenant mapping
- overview dashboard
- sessions list and detail
- knowledge base CRUD
- brand voice editor
- WhatsApp integration status and setup
- governance log viewer
- basic metrics
- billing and subscription links

The first version should not deeply build Slack, Shopify, or Zendesk. They can appear as disabled upcoming integration cards.

## Pages

### `/login`

Purpose: let a paid client sign in.

Needs:

- Google login
- email fallback
- redirect to onboarding when setup is incomplete
- redirect to dashboard when setup and subscription are active

### `/onboarding`

Purpose: guide a paid client through setup before go-live.

Steps:

1. Business profile: company name, website, industry, support email.
2. Brand voice: tone, words to use, words to avoid, escalation style.
3. Knowledge base: manual FAQ input, CSV upload, pasted docs. Website import comes later.
4. WhatsApp integration: Meta or Twilio setup instructions and connection status.
5. Test SVMP: sample customer questions before go-live.
6. Go-live checklist.

### `/dashboard`

Purpose: show whether SVMP is creating value and staying safe.

Needs:

- deflection rate
- human hours saved
- average resolution time
- safety score
- AI resolved vs human escalated chart
- recent activity
- system health
- setup warnings when incomplete

### `/sessions`

Purpose: inspect customer conversations and outcomes.

Needs:

- list of sessions or conversation summaries
- status: resolved, escalated, pending, failed
- transcript or active customer message
- SVMP answer
- matched KB source
- confidence and safety score
- escalation reason
- timestamp and provider

### `/knowledge-base`

Purpose: control the trusted answers SVMP can use.

Needs:

- add, edit, delete FAQ entries
- search and filter by topic or domain
- active and inactive toggle
- bulk import
- test question box
- last updated timestamp
- later: AI-suggested KB entries from site or docs

### `/brand-voice`

Purpose: control how SVMP sounds.

Needs:

- tone description
- words to use
- words to avoid
- example replies
- escalation message style
- preview with a test question
- later: version history

### `/governance`

Purpose: expose the trust and audit layer.

Needs:

- escalations
- low-confidence answers
- blocked or unsafe responses
- why SVMP answered or escalated
- source KB entries used
- similarity, groundedness, and safety scores
- later: export logs

### `/metrics`

Purpose: show deeper analytics.

Needs:

- automation and deflection trend
- escalation trend
- response time by hour
- topic distribution
- CSAT breakdown if collected
- volume by day, week, or month
- KB gap insights

### `/integrations`

Purpose: show connected and future channels.

Needs:

- WhatsApp card: connected, healthy, last sync, configure
- Slack card: upcoming
- Shopify card: upcoming
- Zendesk card: upcoming

Only WhatsApp should behave as a real MVP integration.

### `/settings`

Purpose: manage tenant administration.

Needs:

- business profile
- users and team invites
- roles and permissions
- billing and subscription
- API and webhook info
- confidence threshold
- support handoff destination later

## Build Milestones

### Milestone 1: Contracts

Create the product, API, auth, billing, and schema contracts in docs. This makes every later code change easier to review.

### Milestone 2: Backend Guardrails

Add backend auth, tenant resolution, role checks, and subscription checks. Dashboard APIs must be protected before the frontend depends on them.

### Milestone 3: Backend Data APIs

Add dashboard read and write APIs using repository contracts, not direct route-level Mongo queries.

### Milestone 4: Frontend Shell

Create the Next.js app, dashboard layout, navigation, login flow, loading states, empty states, and error states.

### Milestone 5: MVP Pages

Build overview, sessions, knowledge base, brand voice, governance, metrics, integrations, and settings.

### Milestone 6: Billing And Onboarding

Wire manual pilot billing, tenant access approval, and the onboarding wizard. Payment-provider checkout can be added after incorporation.

### Milestone 7: Staging Rollout

Deploy staging, connect a test tenant, validate auth, tenant isolation, manual billing status, WhatsApp status, and dashboard data.

## Review Rule

Each implementation slice should be small enough to review by opening a few files. When code changes begin, every slice should include:

- what changed
- why it changed
- which files matter
- how to test it
- what remains intentionally unfinished
