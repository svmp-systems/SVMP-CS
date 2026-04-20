import { WhatsAppConfigPanel } from "@/components/portal/whatsapp-config-panel";
import { PageHeader } from "@/components/portal/page-header";
import { PortalErrorScreen } from "@/components/portal/portal-error-screen";
import { getServerApi } from "@/services/api/server";
import { ApiError } from "@/services/api/shared";
import { redirect } from "next/navigation";

export default async function IntegrationsPage() {
  try {
    const api = await getServerApi();
    const { integrations } = await api.getIntegrations();

    return (
      <>
        <PageHeader
          eyebrow="Integrations"
          title="Connect the channels SVMP CS is allowed to operate."
          copy="WhatsApp is the current live support channel. Any additional providers stay clearly marked until they are fully connected for this tenant."
        />
        <WhatsAppConfigPanel initialIntegrations={integrations} />
      </>
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 402) {
      redirect("/settings?billing=required");
    }
    return <PortalErrorScreen error={error} />;
  }
}
