import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/panel";
import { StatusBadge, statusTone } from "@/components/portal/status-badge";
import { api } from "@/lib/api-client";

export default async function IntegrationsPage() {
  const { integrations } = await api.getIntegrations();
  const whatsapp = integrations.find((integration) => integration.provider === "whatsapp");
  const future = integrations.filter((integration) => integration.provider !== "whatsapp");

  return (
    <>
      <PageHeader
        eyebrow="Integrations"
        title="Connect the channels SVMP is allowed to operate."
        copy="WhatsApp is the live MVP channel. Future integrations stay clearly marked until they are actually connected."
        action={
          <button className="rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-paper hover:bg-pine">
            Configure WhatsApp
          </button>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
        <Panel title="WhatsApp" eyebrow="Live channel">
          {whatsapp ? (
            <div className="space-y-5">
              <div className="flex flex-wrap items-start justify-between gap-3 rounded-[8px] border border-line bg-paper p-5">
                <div>
                  <p className="text-lg font-semibold">{whatsapp.title}</p>
                  <p className="mt-2 text-sm leading-6 text-ink/64">{whatsapp.detail}</p>
                </div>
                <StatusBadge tone={statusTone(whatsapp.status)}>{whatsapp.status}</StatusBadge>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-[8px] border border-line p-4">
                  <p className="text-sm text-ink/56">Health</p>
                  <p className="mt-2 font-semibold">{whatsapp.health}</p>
                </div>
                <div className="rounded-[8px] border border-line p-4">
                  <p className="text-sm text-ink/56">Last sync</p>
                  <p className="mt-2 font-semibold">{whatsapp.lastSync ?? "Not synced"}</p>
                </div>
              </div>

              <div className="rounded-[8px] border border-line p-4">
                <p className="text-sm font-semibold">Webhook endpoint</p>
                <p className="mt-2 break-all rounded-[8px] bg-mist px-3 py-2 text-sm text-ink/70">
                  https://api.svmpsystems.com/webhook
                </p>
                <p className="mt-3 text-sm leading-6 text-ink/62">
                  Provider events are verified, deduplicated, and written before tenant workflows run.
                </p>
              </div>
            </div>
          ) : null}
        </Panel>

        <Panel title="Upcoming integrations" eyebrow="Not live in MVP">
          <div className="space-y-3">
            {future.map((integration) => (
              <article key={integration.provider} className="rounded-[8px] border border-line p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="font-semibold">{integration.title}</h3>
                  <StatusBadge tone={statusTone(integration.status)}>{integration.status.replace("_", " ")}</StatusBadge>
                </div>
                <p className="mt-3 text-sm leading-6 text-ink/64">{integration.detail}</p>
              </article>
            ))}
          </div>
        </Panel>
      </div>
    </>
  );
}
