import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { StatusBadge, statusTone } from "@/components/portal/status-badge";
import {
  createCheckoutSessionAction,
  createPortalSessionAction,
  updateTenantAction,
} from "@/lib/actions";
import { api } from "@/lib/api-client";

const team = [
  { name: "Pranav", email: "owner@stayparfums.com", role: "owner" },
  { name: "Support Lead", email: "admin@stayparfums.com", role: "admin" },
  { name: "Ops Analyst", email: "analyst@stayparfums.com", role: "analyst" },
];

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const params = await searchParams;
  const tenant = await api.getTenant();
  const settings = tenant.settings ?? {};

  return (
    <>
      <PageHeader
        eyebrow="Settings"
        title="Tenant controls for the paid account."
        copy="Manage business profile, users, billing, webhook details, confidence thresholds, and support handoff rules."
      />

      {params.error ? (
        <div className="mb-6 rounded-[8px] border border-berry/20 bg-berry/10 p-4 text-sm font-semibold text-berry">
          {params.error}
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
        <div className="space-y-6">
          <Panel title="Business profile" eyebrow={tenant.tenantId}>
            <form action={updateTenantAction} className="grid gap-4 md:grid-cols-2">
              <label className="grid gap-2">
                <span className="text-sm font-semibold">Company name</span>
                <input name="tenantName" className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine" defaultValue={tenant.tenantName} />
              </label>
              <label className="grid gap-2">
                <span className="text-sm font-semibold">Website</span>
                <input name="websiteUrl" className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine" defaultValue={tenant.websiteUrl} />
              </label>
              <label className="grid gap-2">
                <span className="text-sm font-semibold">Support email</span>
                <input name="supportEmail" className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine" defaultValue={tenant.supportEmail} />
              </label>
              <label className="grid gap-2">
                <span className="text-sm font-semibold">Industry</span>
                <input name="industry" className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine" defaultValue={tenant.industry ?? "Fragrance"} />
              </label>
              <label className="grid gap-2">
                <span className="text-sm font-semibold">Tenant ID</span>
                <input className="h-11 rounded-[8px] border border-line bg-mist px-3 text-sm text-ink/60" defaultValue={tenant.tenantId} readOnly />
              </label>
              <label className="grid gap-2">
                <span className="text-sm font-semibold">Confidence threshold</span>
                <input
                  name="confidenceThreshold"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  className="h-11 rounded-[8px] border border-line bg-paper px-3 text-sm outline-none focus:border-pine"
                  defaultValue={settings.confidenceThreshold ?? tenant.confidenceThreshold ?? 0.75}
                />
              </label>
              <label className="flex items-center gap-2 text-sm font-semibold md:col-span-2">
                <input name="autoAnswerEnabled" type="checkbox" defaultChecked={settings.autoAnswerEnabled ?? true} />
                Auto-answer when confidence passes threshold
              </label>
              <button className="w-fit rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine md:col-span-2">
                Save settings
              </button>
            </form>
          </Panel>

          <Panel title="Users and roles" eyebrow="Team access">
            <div className="space-y-3">
              {team.map((member) => (
                <div key={member.email} className="flex flex-wrap items-center justify-between gap-3 rounded-[8px] border border-line p-4">
                  <div>
                    <p className="font-semibold">{member.name}</p>
                    <p className="mt-1 text-sm text-ink/56">{member.email}</p>
                  </div>
                  <StatusBadge tone={statusTone(member.role)}>{member.role}</StatusBadge>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel title="Billing" eyebrow="Subscription">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-[8px] border border-line bg-paper p-4">
              <div>
                <p className="font-semibold">Paid access</p>
                <p className="mt-2 text-sm text-ink/60">Dashboard APIs are gated by tenant subscription status.</p>
              </div>
              <StatusBadge tone={statusTone(tenant.subscriptionStatus)}>{tenant.subscriptionStatus}</StatusBadge>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <form action={createCheckoutSessionAction}>
                <button className="rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine">
                  Start checkout
                </button>
              </form>
              <form action={createPortalSessionAction}>
                <button className="rounded-[8px] border border-line bg-white px-4 py-3 text-sm font-semibold hover:border-ink">
                  Open billing portal
                </button>
              </form>
            </div>
          </Panel>

          <Panel title="API and webhooks" eyebrow="Endpoints">
            <div className="space-y-3 text-sm">
              <div>
                <p className="font-semibold">Dashboard API</p>
                <p className="mt-2 break-all rounded-[8px] bg-mist px-3 py-2 text-ink/68">
                  https://api.svmpsystems.com/api
                </p>
              </div>
              <div>
                <p className="font-semibold">WhatsApp webhook</p>
                <p className="mt-2 break-all rounded-[8px] bg-mist px-3 py-2 text-ink/68">
                  https://api.svmpsystems.com/webhook
                </p>
              </div>
              <div>
                <p className="font-semibold">Stripe webhook</p>
                <p className="mt-2 break-all rounded-[8px] bg-mist px-3 py-2 text-ink/68">
                  https://api.svmpsystems.com/api/billing/webhook
                </p>
              </div>
            </div>
          </Panel>

          <Panel title="Automation controls" eyebrow="Runtime settings">
            <div className="mt-4 rounded-[8px] border border-line bg-paper p-4">
              <p className="font-semibold">Auto-answering</p>
              <p className="mt-2 text-sm leading-6 text-ink/62">
                Answers below threshold escalate. Provider credentials stay server-side.
              </p>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
