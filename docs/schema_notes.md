# Schema Notes

## Core Tables

- `tenants`
  canonical tenant profile, domain config, billing summary, and JSON payload
- `tenant_memberships`
  portal access control and role resolution
- `tenant_provider_identities`
  maps provider channel identities to tenants for webhook routing
- `session_state`
  active debounce-window session state
- `knowledge_base_entries`
  tenant FAQ corpus plus shared materialized entries
- `governance_logs`
  immutable decision logs
- `integration_status`
  safe operational status for integrations
- `audit_logs`
  dashboard write audit trail
- `billing_subscriptions`
  Stripe subscription linkage and state
- `provider_events`
  webhook idempotency records

## Important Constraints

- one open session per tenant/client/user identity
- unique provider identity mapping per tenant/provider/identity
- unique membership ids with update-friendly role and status fields
- unique provider events per provider/event id pair

## JSON Usage

The schema is relational first, with targeted JSON support where it helps:

- `tenants.payload`
  preserves flexible tenant metadata
- `tenant_memberships.permissions`
  stores role-derived permission lists
- audit and governance metadata fields
  preserve structured context without schema churn

## Operational Notes

- `session_state` is designed for atomic acquisition in Workflow B.
- `provider_events` makes webhook handlers safe to retry.
- dashboard APIs should read tenant scope through `tenant_memberships`, never from client-submitted tenant ids.
